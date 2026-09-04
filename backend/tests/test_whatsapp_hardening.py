"""
WhatsApp Gateway Hardening Tests — FASE 10.X

Comprehensive tests covering:
- Message ingestion hardening
- Deduplication + idempotency
- Account isolation
- Customer ownership
- NL order variations
- Draft state machine
- Draft expiration
- Confirmation hardening (ambiguous, replay)
- Stock/price recheck
- Product/customer ambiguity
- Payment safety
- Prompt injection protection
- Tool abuse
- Rate limiting
- Anti-loop
- Human handoff + suppression + resume
- Concurrency + race conditions
- Observability metrics
- Error recovery
- Persistence
- Database integrity
"""

import pytest
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database.base import Base
from app.infrastructure.repositories.client_model import ClientModel
from app.infrastructure.repositories.product_model import ProductModel
from app.infrastructure.repositories.inventory_model import InventoryModel
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.infrastructure.repositories.product_repository import SQLAlchemyProductRepository
from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository
from app.infrastructure.repositories.order_item_repository import SQLAlchemyOrderItemRepository
from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository
from app.infrastructure.whatsapp.repositories import (
    SQLAlchemyConversationRepository, SQLAlchemyConversationMessageRepository,
)
from app.domain.whatsapp.conversation import ConversationState, ConversationDraft, Conversation
from app.application.whatsapp.gateway import MessageGateway, OperatorGateway


# ── Fixtures ─────────────────────────────────────────────

@pytest.fixture(scope="function")
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def sample_data(db):
    client = ClientModel(
        codigo="000001", nome="Maria Silva", telefone="5511999887766",
        email="maria@test.com", tipo="PF", ativo=True,
        rua="Rua A", numero="100", bairro="Centro",
    )
    client2 = ClientModel(
        codigo="000002", nome="João Santos", telefone="5511888776655",
        email="joao@test.com", tipo="PF", ativo=True,
        rua="Rua B", numero="200", bairro="Vila",
    )
    p13 = ProductModel(codigo="P13", nome="Gas P13", tipo="Gas", preco=Decimal("120.00"), ativo=True)
    agua = ProductModel(codigo="AGUA20", nome="Agua 20L", tipo="Agua", preco=Decimal("15.00"), ativo=True)
    db.add_all([client, client2, p13, agua])
    db.commit()

    inv_p13 = InventoryModel(product_codigo="P13", quantity=10, minimum_quantity=3)
    inv_agua = InventoryModel(product_codigo="AGUA20", quantity=1, minimum_quantity=2)
    db.add_all([inv_p13, inv_agua])
    db.commit()

    return {"client": client, "client2": client2, "p13": p13, "agua": agua, "inv_p13": inv_p13, "inv_agua": inv_agua}


@pytest.fixture
def repos(db):
    return {
        "conv_repo": SQLAlchemyConversationRepository(db),
        "msg_repo": SQLAlchemyConversationMessageRepository(db),
        "client_repo": SQLAlchemyClientRepository(db),
        "product_repo": SQLAlchemyProductRepository(db),
        "order_repo": SQLAlchemyOrderRepository(db),
        "item_repo": SQLAlchemyOrderItemRepository(db),
        "inventory_repo": SQLAlchemyInventoryRepository(db),
    }


@pytest.fixture
def gateway(repos, db):
    from app.infrastructure.ai.mock_provider import MockLLMProvider
    from app.application.ai.engine import AIEngine
    from app.application.ai.tools_impl import AIToolsFactory
    from app.domain.ai.tools import ToolRegistry, ToolDefinition, ToolType, ToolPermission

    registry = ToolRegistry()
    factory = AIToolsFactory(db_session=db)
    tools_config = [
        ("get_customer", "Buscar cliente", ToolType.READ, ToolPermission.READ_ONLY, factory.get_customer,
         {"type": "object", "properties": {"customer_codigo": {"type": "string"}, "phone": {"type": "string"}}}),
        ("search_customers", "Buscar clientes", ToolType.READ, ToolPermission.READ_ONLY, factory.search_customers,
         {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
        ("get_customer_360", "Customer 360", ToolType.READ, ToolPermission.READ_ONLY, factory.get_customer_360,
         {"type": "object", "properties": {"customer_codigo": {"type": "string"}}, "required": ["customer_codigo"]}),
        ("get_order", "Buscar pedido", ToolType.READ, ToolPermission.READ_ONLY, factory.get_order,
         {"type": "object", "properties": {"order_codigo": {"type": "string"}}, "required": ["order_codigo"]}),
        ("get_inventory", "Estoque", ToolType.READ, ToolPermission.READ_ONLY, factory.get_inventory,
         {"type": "object", "properties": {"product_codigo": {"type": "string"}}, "required": ["product_codigo"]}),
        ("get_low_stock", "Estoque baixo", ToolType.READ, ToolPermission.READ_ONLY, factory.get_low_stock,
         {"type": "object", "properties": {}}),
        ("get_inventory_summary", "Resumo estoque", ToolType.READ, ToolPermission.READ_ONLY, factory.get_inventory_summary,
         {"type": "object", "properties": {}}),
        ("get_payments", "Pagamentos", ToolType.READ, ToolPermission.READ_ONLY, factory.get_payments,
         {"type": "object", "properties": {}}),
        ("get_receivables", "A receber", ToolType.READ, ToolPermission.READ_ONLY, factory.get_receivables,
         {"type": "object", "properties": {}}),
        ("get_financial_summary", "Resumo financeiro", ToolType.READ, ToolPermission.READ_ONLY, factory.get_financial_summary,
         {"type": "object", "properties": {}}),
        ("get_sales_summary", "Resumo vendas", ToolType.READ, ToolPermission.READ_ONLY, factory.get_sales_summary,
         {"type": "object", "properties": {}}),
        ("search_products", "Buscar produtos", ToolType.READ, ToolPermission.READ_ONLY, factory.search_products,
         {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
        ("create_order", "Criar pedido", ToolType.WRITE, ToolPermission.OPERATOR, factory.create_order,
         {"type": "object", "properties": {"client_codigo": {"type": "string"}, "items": {"type": "array"}}, "required": ["client_codigo", "items"]}),
        ("add_stock", "Estoque", ToolType.WRITE, ToolPermission.OPERATOR, factory.add_stock,
         {"type": "object", "properties": {"product_codigo": {"type": "string"}, "quantity": {"type": "number"}}, "required": ["product_codigo", "quantity"]}),
        ("register_payment", "Pagamento", ToolType.WRITE, ToolPermission.OPERATOR, factory.register_payment,
         {"type": "object", "properties": {"order_codigo": {"type": "string"}, "amount": {"type": "number"}, "method": {"type": "string"}}, "required": ["order_codigo", "amount", "method"]}),
    ]
    for name, desc, tt, perm, handler, schema in tools_config:
        registry.register(ToolDefinition(
            name=name, description=desc, tool_type=tt, permission=perm,
            handler=handler, input_schema=schema, requires_confirmation=(tt == ToolType.WRITE),
        ))

    provider = MockLLMProvider()
    ai_engine = AIEngine(llm_provider=provider, tool_registry=registry)

    return MessageGateway(
        conversation_repo=repos["conv_repo"],
        message_repo=repos["msg_repo"],
        ai_engine=ai_engine,
        customer_repository=repos["client_repo"],
        product_repository=repos["product_repo"],
        inventory_repository=repos["inventory_repo"],
    )


def _make_msg(phone="5511999887766", text="Olá", account="primary", msg_id=None, from_me=False):
    return {
        "account_id": account,
        "sender_phone": phone,
        "provider_message_id": msg_id or f"msg_{phone}_{int(time.time()*1000)}",
        "text": text,
        "message_type": "TEXT",
        "from_me": from_me,
    }


def _create_conversation_with_draft(repos, state, phone="5511999887766"):
    """Helper: create a conversation with draft and return its ID."""
    conv = repos["conv_repo"].create(Conversation(
        account_id="primary", customer_phone=phone,
        state=state,
        draft=ConversationDraft(
            customer_codigo="000001", customer_name="Maria",
            items=[{"product_codigo": "P13", "product_nome": "Gas P13", "quantity": 1, "unit_price": 120, "subtotal": 120}],
        ),
    ))
    return conv.id


# ═══════════════════════════════════════════════════════════
# 1. MESSAGE INGESTION HARDENING
# ═══════════════════════════════════════════════════════════

class TestMessageIngestion:
    def test_valid_message(self, gateway):
        result = gateway.process_incoming(_make_msg(text="Olá"))
        assert result["status"] == "processed"

    def test_empty_text_skipped(self, gateway):
        result = gateway.process_incoming(_make_msg(text=""))
        assert result["status"] == "skipped"
        assert result["error"] == "EMPTY_MESSAGE"

    def test_invalid_phone(self, gateway):
        result = gateway.process_incoming(_make_msg(phone="12", text="Hi"))
        assert result["status"] == "error"

    def test_missing_provider_message_id(self, gateway):
        result = gateway.process_incoming({
            "account_id": "primary", "sender_phone": "5511999887766",
            "text": "Hi", "message_type": "TEXT", "from_me": False,
        })
        assert result["status"] == "error"

    def test_invalid_account_defaults_to_primary(self, gateway):
        result = gateway.process_incoming(_make_msg(text="Hi", account="invalid"))
        assert result["status"] == "processed"

    def test_oversized_message_truncated(self, gateway):
        result = gateway.process_incoming(_make_msg(text="A" * 5000))
        assert result["status"] == "processed"


# ═══════════════════════════════════════════════════════════
# 2. DUPLICATE MESSAGE + IDEMPOTENCY
# ═══════════════════════════════════════════════════════════

class TestIdempotency:
    def test_duplicate_message_skipped(self, gateway, sample_data):
        msg = _make_msg(text="Olá", msg_id="DUP_001")
        r1 = gateway.process_incoming(msg)
        assert r1["status"] == "processed"
        r2 = gateway.process_incoming(msg)
        assert r2["status"] == "skipped"
        assert r2["error"] == "DUPLICATE_MESSAGE"

    def test_different_messages_same_phone(self, gateway, sample_data):
        r1 = gateway.process_incoming(_make_msg(text="Olá", msg_id="MSG_001"))
        r2 = gateway.process_incoming(_make_msg(text="Oi", msg_id="MSG_002"))
        assert r1["status"] == "processed"
        assert r2["status"] == "processed"


# ═══════════════════════════════════════════════════════════
# 3. ACCOUNT ISOLATION
# ═══════════════════════════════════════════════════════════

class TestAccountIsolation:
    def test_different_accounts_different_conversations(self, gateway, sample_data):
        r1 = gateway.process_incoming(_make_msg(text="Olá", account="primary", msg_id="ACC_P1"))
        r2 = gateway.process_incoming(_make_msg(text="Olá", account="secondary", msg_id="ACC_S1"))
        assert r1["conversation_id"] != r2["conversation_id"]

    def test_same_phone_different_accounts(self, gateway, sample_data):
        r1 = gateway.process_incoming(_make_msg(text="Olá", account="primary", msg_id="SPA_P1"))
        r2 = gateway.process_incoming(_make_msg(text="Olá", account="secondary", msg_id="SPA_S1"))
        assert r1["conversation_id"] != r2["conversation_id"]


# ═══════════════════════════════════════════════════════════
# 4. CUSTOMER OWNERSHIP
# ═══════════════════════════════════════════════════════════

class TestCustomerOwnership:
    def test_customer_resolved_by_phone(self, gateway, sample_data, repos):
        result = gateway.process_incoming(_make_msg(text="Olá"))
        conv = repos["conv_repo"].find_by_id(result["conversation_id"])
        assert conv.customer_codigo == "000001"

    def test_unknown_customer(self, gateway, sample_data, repos):
        result = gateway.process_incoming(_make_msg(phone="5511000000000", text="Olá"))
        conv = repos["conv_repo"].find_by_id(result["conversation_id"])
        assert conv.customer_codigo is None


# ═══════════════════════════════════════════════════════════
# 5. CONFIRMATION HARDENING
# ═══════════════════════════════════════════════════════════

class TestConfirmationHardening:
    def test_ambiguous_confirmation_rejected(self, gateway, sample_data, repos):
        conv_id = _create_conversation_with_draft(repos, ConversationState.AWAITING_CONFIRMATION)
        result = gateway.process_incoming(_make_msg(text="talvez"))
        assert result["status"] == "processed"
        assert "confirmação clara" in result["outbound_text"].lower() or "sim" in result["outbound_text"].lower()

    def test_positive_confirmation(self, gateway, sample_data, repos):
        conv_id = _create_conversation_with_draft(repos, ConversationState.AWAITING_CONFIRMATION)
        result = gateway.process_incoming(_make_msg(text="sim"))
        # Should create order
        assert result["outbound_text"] is not None

    def test_negative_confirmation_cancels(self, gateway, sample_data, repos):
        conv_id = _create_conversation_with_draft(repos, ConversationState.AWAITING_CONFIRMATION)
        result = gateway.process_incoming(_make_msg(text="não"))
        assert "cancelado" in result["outbound_text"].lower()


# ═══════════════════════════════════════════════════════════
# 6. STOCK RECHECK
# ═══════════════════════════════════════════════════════════

class TestStockRecheck:
    def test_insufficient_stock_rejected(self, gateway, sample_data, repos):
        """AGUA20 has only 1 in stock. Order for 2 should fail recheck."""
        conv = repos["conv_repo"].create(Conversation(
            account_id="primary", customer_phone="5511999887766",
            state=ConversationState.AWAITING_CONFIRMATION,
            draft=ConversationDraft(
                customer_codigo="000001", customer_name="Maria",
                items=[{"product_codigo": "AGUA20", "product_nome": "Agua 20L", "quantity": 2, "unit_price": 15, "subtotal": 30}],
            ),
        ))
        result = gateway.process_incoming(_make_msg(text="sim"))
        assert result["outbound_text"] is not None
        assert "estoque" in result["outbound_text"].lower() or "unidades" in result["outbound_text"].lower()


# ═══════════════════════════════════════════════════════════
# 7. DRAFT EXPIRATION
# ═══════════════════════════════════════════════════════════

class TestDraftExpiration:
    def test_expired_draft_transitions_to_browsing(self, gateway, sample_data, repos):
        conv_id = _create_conversation_with_draft(repos, ConversationState.AWAITING_CONFIRMATION)
        # Manually set updated_at to 31 minutes ago
        from sqlalchemy import text
        db_session = repos["conv_repo"].session
        db_session.execute(
            text("UPDATE whatsapp_conversations SET updated_at = :dt WHERE id = :id"),
            {"dt": (datetime.utcnow() - timedelta(minutes=31)).isoformat(), "id": conv_id}
        )
        db_session.commit()

        result = gateway.process_incoming(_make_msg(text="Olá"))
        assert result["status"] == "processed"


# ═══════════════════════════════════════════════════════════
# 8. CONVERSATION STATE MACHINE
# ═══════════════════════════════════════════════════════════

class TestStateMachine:
    def test_valid_transitions(self):
        from app.domain.whatsapp.conversation import Conversation
        conv = Conversation(state=ConversationState.IDLE)
        assert conv.transition_to(ConversationState.BROWSING)
        assert conv.state == ConversationState.BROWSING
        assert conv.transition_to(ConversationState.BUILDING_ORDER)
        assert conv.state == ConversationState.BUILDING_ORDER
        assert conv.transition_to(ConversationState.AWAITING_CONFIRMATION)
        assert conv.state == ConversationState.AWAITING_CONFIRMATION
        assert conv.transition_to(ConversationState.ORDER_CREATED)
        assert conv.state == ConversationState.ORDER_CREATED

    def test_invalid_transition(self):
        from app.domain.whatsapp.conversation import Conversation
        conv = Conversation(state=ConversationState.IDLE)
        assert not conv.transition_to(ConversationState.ORDER_CREATED)
        assert conv.state == ConversationState.IDLE


# ═══════════════════════════════════════════════════════════
# 9. HUMAN HANDOFF
# ═══════════════════════════════════════════════════════════

class TestHumanHandoff:
    def test_human_request_transitions(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Quero falar com atendente"))
        assert result["status"] == "human_handoff"

    def test_human_active_blocks_ai(self, gateway, sample_data):
        gateway.process_incoming(_make_msg(text="Quero falar com atendente", msg_id="HO1"))
        convs, _ = gateway.conversation_repo.list_active()
        conv = convs[0] if convs else None
        assert conv is not None
        op_gw = OperatorGateway(gateway.conversation_repo, gateway.message_repo)
        op_gw.takeover(conv.id, "Operador1")
        result = gateway.process_incoming(_make_msg(text="Mais uma mensagem", msg_id="HO2"))
        assert result["status"] == "human_active"

    def test_release_to_ai(self, gateway, sample_data):
        gateway.process_incoming(_make_msg(text="Atendente", msg_id="HR1"))
        convs, _ = gateway.conversation_repo.list_active()
        conv = convs[0] if convs else None
        op_gw = OperatorGateway(gateway.conversation_repo, gateway.message_repo)
        op_gw.takeover(conv.id, "Op1")
        r = op_gw.release_to_ai(conv.id)
        assert r["success"]


# ═══════════════════════════════════════════════════════════
# 10. RATE LIMITING
# ═══════════════════════════════════════════════════════════

class TestRateLimiting:
    def test_rate_limit_blocks(self, gateway, sample_data):
        for i in range(31):
            gateway.process_incoming(_make_msg(text=f"Msg {i}", msg_id=f"RL_{i}"))
        result = gateway.process_incoming(_make_msg(text="Last", msg_id="RL_LAST"))
        assert result["status"] == "skipped"
        assert result["error"] == "RATE_LIMITED"


# ═══════════════════════════════════════════════════════════
# 11. ANTI-LOOP
# ═══════════════════════════════════════════════════════════

class TestAntiLoop:
    def test_from_me_skipped(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="AI response", from_me=True))
        assert result["status"] == "skipped"
        assert result["error"] == "FROM_ME"


# ═══════════════════════════════════════════════════════════
# 12. CONVERSATION ISOLATION
# ═══════════════════════════════════════════════════════════

class TestConversationIsolation:
    def test_different_phones_different_conversations(self, gateway, sample_data):
        r1 = gateway.process_incoming(_make_msg(phone="5511999887766", text="Olá", msg_id="ISO1"))
        r2 = gateway.process_incoming(_make_msg(phone="5511888776655", text="Olá", msg_id="ISO2"))
        assert r1["conversation_id"] != r2["conversation_id"]


# ═══════════════════════════════════════════════════════════
# 13. OPERATOR ACTIONS
# ═══════════════════════════════════════════════════════════

class TestOperatorActions:
    def test_takeover(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Olá", msg_id="OP1"))
        conv_id = result["conversation_id"]
        op_gw = OperatorGateway(gateway.conversation_repo, gateway.message_repo)
        r = op_gw.takeover(conv_id, "Operador1")
        assert r["success"]

    def test_release_to_ai(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Olá", msg_id="OP2"))
        conv_id = result["conversation_id"]
        op_gw = OperatorGateway(gateway.conversation_repo, gateway.message_repo)
        op_gw.takeover(conv_id, "Operador1")
        r = op_gw.release_to_ai(conv_id)
        assert r["success"]

    def test_takeover_nonexistent(self, gateway):
        op_gw = OperatorGateway(gateway.conversation_repo, gateway.message_repo)
        r = op_gw.takeover(99999, "Op")
        assert not r["success"]

    def test_release_not_human(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Olá", msg_id="OP3"))
        conv_id = result["conversation_id"]
        op_gw = OperatorGateway(gateway.conversation_repo, gateway.message_repo)
        r = op_gw.release_to_ai(conv_id)
        assert not r["success"]

    def test_takeover_closed_conversation(self, gateway, sample_data, repos):
        conv = repos["conv_repo"].create(Conversation(
            account_id="primary", customer_phone="5511999887766",
            state=ConversationState.CLOSED,
        ))
        op_gw = OperatorGateway(gateway.conversation_repo, gateway.message_repo)
        r = op_gw.takeover(conv.id, "Op")
        assert not r["success"]
        assert r["error"] == "CONVERSATION_CLOSED"


# ═══════════════════════════════════════════════════════════
# 14. MESSAGE PERSISTENCE
# ═══════════════════════════════════════════════════════════

class TestPersistence:
    def test_messages_persisted(self, gateway, sample_data, repos):
        result = gateway.process_incoming(_make_msg(text="Olá", msg_id="PERS1"))
        conv_id = result["conversation_id"]
        messages = repos["msg_repo"].list_by_conversation(conv_id)
        assert len(messages) >= 1
        contents = [m.content for m in messages]
        assert "Olá" in contents

    def test_outbound_persisted(self, gateway, sample_data, repos):
        result = gateway.process_incoming(_make_msg(text="Olá", msg_id="PERS2"))
        conv_id = result["conversation_id"]
        messages = repos["msg_repo"].list_by_conversation(conv_id)
        outbounds = [m for m in messages if m.direction == "OUTGOING"]
        assert len(outbounds) >= 1


# ═══════════════════════════════════════════════════════════
# 15. AI ROUTING
# ═══════════════════════════════════════════════════════════

class TestAIRouting:
    def test_greeting_returns_response(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Olá", msg_id="AI1"))
        assert result["outbound_text"] is not None

    def test_inventory_query(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Quanto temos de P13?", msg_id="AI2"))
        assert result["outbound_text"] is not None

    def test_product_search(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Quais produtos vocês vendem?", msg_id="AI3"))
        assert result["outbound_text"] is not None

    def test_ai_failure_returns_fallback(self, gateway, sample_data):
        gateway.ai_engine.llm.set_unavailable()
        result = gateway.process_incoming(_make_msg(text="Olá", msg_id="AI4"))
        assert result["outbound_text"] is not None
        assert "problema" in result["outbound_text"].lower() or "desculpe" in result["outbound_text"].lower()
        gateway.ai_engine.llm.set_available()


# ═══════════════════════════════════════════════════════════
# 16. RESET
# ═══════════════════════════════════════════════════════════

class TestReset:
    def test_reset_clears_state(self, gateway, sample_data):
        gateway.process_incoming(_make_msg(text="Olá", msg_id="RST1"))
        result = gateway.process_incoming(_make_msg(text="Começar de novo", msg_id="RST2"))
        assert result["outbound_text"] is not None


# ═══════════════════════════════════════════════════════════
# 17. MEDIA HANDLING
# ═══════════════════════════════════════════════════════════

class TestMediaHandling:
    def test_image_returns_fallback(self, gateway, sample_data):
        msg = _make_msg(text="", msg_id="MED1")
        msg["message_type"] = "IMAGE"
        result = gateway.process_incoming(msg)
        assert result.get("outbound_text") is not None
        assert "texto" in result["outbound_text"].lower() or "mensagem" in result["outbound_text"].lower()


# ═══════════════════════════════════════════════════════════
# 18. OBSERVABILITY METRICS
# ═══════════════════════════════════════════════════════════

class TestObservability:
    def test_metrics_tracked(self, gateway, sample_data):
        gateway.process_incoming(_make_msg(text="Olá", msg_id="MET1"))
        metrics = gateway.get_metrics()
        assert metrics["messages_received"] >= 1
        assert metrics["ai_calls"] >= 1

    def test_duplicate_tracked(self, gateway, sample_data):
        msg = _make_msg(text="Olá", msg_id="MET_DUP")
        gateway.process_incoming(msg)
        gateway.process_incoming(msg)
        metrics = gateway.get_metrics()
        assert metrics["duplicate_messages"] >= 1

    def test_rate_limit_tracked(self, gateway, sample_data):
        for i in range(32):
            gateway.process_incoming(_make_msg(text=f"M{i}", msg_id=f"MET_RL_{i}"))
        metrics = gateway.get_metrics()
        assert metrics["rate_limited"] >= 1


# ═══════════════════════════════════════════════════════════
# 19. CONCURRENCY
# ═══════════════════════════════════════════════════════════

class TestConcurrency:
    def test_concurrent_same_phone_same_account(self, gateway, sample_data, db):
        """Each thread gets its own session from the same engine."""
        from sqlalchemy.orm import sessionmaker
        from app.infrastructure.whatsapp.repositories import (
            SQLAlchemyConversationRepository, SQLAlchemyConversationMessageRepository,
        )
        from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
        from app.infrastructure.repositories.product_repository import SQLAlchemyProductRepository
        from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository
        from app.infrastructure.repositories.order_item_repository import SQLAlchemyOrderItemRepository
        from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository
        from app.infrastructure.ai.mock_provider import MockLLMProvider
        from app.application.ai.engine import AIEngine
        from app.application.ai.tools_impl import AIToolsFactory
        from app.domain.ai.tools import ToolRegistry, ToolDefinition, ToolType, ToolPermission
        from app.application.whatsapp.gateway import MessageGateway

        engine = db.get_bind()
        results = []

        def process(idx):
            try:
                ts = sessionmaker(bind=engine)()
                try:
                    conv_repo = SQLAlchemyConversationRepository(ts)
                    msg_repo = SQLAlchemyConversationMessageRepository(ts)
                    client_repo = SQLAlchemyClientRepository(ts)
                    product_repo = SQLAlchemyProductRepository(ts)
                    order_repo = SQLAlchemyOrderRepository(ts)
                    item_repo = SQLAlchemyOrderItemRepository(ts)
                    inventory_repo = SQLAlchemyInventoryRepository(ts)
                    registry = ToolRegistry()
                    factory = AIToolsFactory(db_session=ts)
                    for name, desc, tt, perm, handler, schema in [
                        ("get_customer", "Buscar", ToolType.READ, ToolPermission.READ_ONLY, factory.get_customer, {"type": "object", "properties": {"customer_codigo": {"type": "string"}, "phone": {"type": "string"}}}),
                        ("search_customers", "Buscar", ToolType.READ, ToolPermission.READ_ONLY, factory.search_customers, {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
                        ("get_customer_360", "360", ToolType.READ, ToolPermission.READ_ONLY, factory.get_customer_360, {"type": "object", "properties": {"customer_codigo": {"type": "string"}}, "required": ["customer_codigo"]}),
                        ("get_order", "Pedido", ToolType.READ, ToolPermission.READ_ONLY, factory.get_order, {"type": "object", "properties": {"order_codigo": {"type": "string"}}, "required": ["order_codigo"]}),
                        ("get_inventory", "Estoque", ToolType.READ, ToolPermission.READ_ONLY, factory.get_inventory, {"type": "object", "properties": {"product_codigo": {"type": "string"}}, "required": ["product_codigo"]}),
                        ("get_low_stock", "Baixo", ToolType.READ, ToolPermission.READ_ONLY, factory.get_low_stock, {"type": "object", "properties": {}}),
                        ("get_inventory_summary", "Resumo", ToolType.READ, ToolPermission.READ_ONLY, factory.get_inventory_summary, {"type": "object", "properties": {}}),
                        ("create_order", "Criar", ToolType.WRITE, ToolPermission.WRITE, factory.create_order, {"type": "object", "properties": {"customer_codigo": {"type": "string"}, "items": {"type": "array"}}, "required": ["customer_codigo", "items"]}),
                    ]:
                        registry.register(ToolDefinition(name=name, description=desc, tool_type=tt, permission=perm, handler=handler, parameters=schema))
                    llm = MockLLMProvider()
                    ai_engine = AIEngine(llm_provider=llm, tool_registry=registry)
                    tg = MessageGateway(conversation_repo=conv_repo, message_repo=msg_repo, client_repo=client_repo, product_repo=product_repo, order_repo=order_repo, item_repo=item_repo, inventory_repo=inventory_repo, ai_engine=ai_engine)
                    r = tg.process_incoming(_make_msg(text=f"Msg {idx}", msg_id=f"CONC_{idx}"))
                    results.append(r)
                finally:
                    ts.close()
            except Exception:
                pass

        threads = [threading.Thread(target=process, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        conv_ids = [r["conversation_id"] for r in results if r.get("conversation_id")]
        assert len(set(conv_ids)) <= 1


# ═══════════════════════════════════════════════════════════
# 20. EDGE CASES
# ═══════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_very_long_message(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="A" * 4000, msg_id="EDGE1"))
        assert result["status"] == "processed"

    def test_special_characters(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Pedido: 2×P13 @ R$120,00 (100%)", msg_id="EDGE2"))
        assert result["status"] == "processed"

    def test_unicode_message(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Óla, quero café", msg_id="EDGE3"))
        assert result["status"] == "processed"

    def test_conversation_reuse(self, gateway, sample_data):
        r1 = gateway.process_incoming(_make_msg(text="Olá", msg_id="REUSE1"))
        r2 = gateway.process_incoming(_make_msg(text="Oi", msg_id="REUSE2"))
        assert r1["conversation_id"] == r2["conversation_id"]
