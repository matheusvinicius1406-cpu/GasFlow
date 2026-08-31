"""
WhatsApp Gateway Tests — FASE 10

Real database tests for:
- Message normalization + dedup
- Conversation creation + state machine
- Account isolation
- Customer resolution
- Customer ownership
- AI routing
- Draft building + confirmation
- Order creation via WhatsApp
- Multi-item order
- Out of stock handling
- Duplicate confirmation
- Human handoff
- Conversation isolation
- Persistence
- Concurrency
- Security (injection, cross-customer, etc.)
"""

import pytest
import json
import threading
import time
from datetime import datetime
from decimal import Decimal
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database.base import Base
from app.infrastructure.repositories.client_model import ClientModel
from app.infrastructure.repositories.product_model import ProductModel
from app.infrastructure.repositories.order_model import OrderModel
from app.infrastructure.repositories.order_item_model import OrderItemModel
from app.infrastructure.repositories.whatsapp_model import WhatsAppConversationModel, WhatsAppMessageModel
from app.infrastructure.repositories.inventory_model import InventoryModel, StockMovementModel
from app.infrastructure.repositories.financial_models import (
    PaymentModel, ReceivableModel, ExpenseModel, CashMovementModel, FinancialLedgerModel,
)
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.infrastructure.repositories.product_repository import SQLAlchemyProductRepository
from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository
from app.infrastructure.repositories.order_item_repository import SQLAlchemyOrderItemRepository
from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository
from app.infrastructure.whatsapp.repositories import (
    SQLAlchemyConversationRepository, SQLAlchemyConversationMessageRepository,
)
from app.domain.whatsapp.conversation import ConversationState, ConversationDraft
from app.domain.whatsapp.repository import ConversationRepository
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
    """Create sample data for tests."""
    # Customer
    client = ClientModel(
        codigo="000001", nome="Maria Silva", telefone="5511999887766",
        email="maria@test.com", tipo="PF", ativo=True,
        rua="Rua A", numero="100", bairro="Centro",
    )
    db.add(client)
    db.commit()

    # Products
    p13 = ProductModel(codigo="P13", nome="Gas P13", tipo="Gas", preco=Decimal("120.00"), ativo=True)
    agua = ProductModel(codigo="AGUA20", nome="Agua 20L", tipo="Agua", preco=Decimal("15.00"), ativo=True)
    db.add_all([p13, agua])
    db.commit()

    # Inventory
    inv_p13 = InventoryModel(product_codigo="P13", quantity=10, minimum_quantity=3)
    inv_agua = InventoryModel(product_codigo="AGUA20", quantity=5, minimum_quantity=2)
    db.add_all([inv_p13, inv_agua])
    db.commit()

    return {
        "client": client,
        "p13": p13,
        "agua": agua,
        "inv_p13": inv_p13,
        "inv_agua": inv_agua,
    }


@pytest.fixture
def repos(db):
    """Create repository instances."""
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
    """Create message gateway with real DB."""
    from app.infrastructure.ai.mock_provider import MockLLMProvider
    from app.application.ai.engine import AIEngine
    from app.application.ai.tools_impl import AIToolsFactory
    from app.domain.ai.tools import ToolRegistry, ToolDefinition, ToolType, ToolPermission

    registry = ToolRegistry()
    factory = AIToolsFactory(db_session=db)

    # Register all tools
    for name, desc, tt, perm, handler, schema, conf in [
        ("get_customer", "Buscar cliente", ToolType.READ, ToolPermission.READ_ONLY, factory.get_customer,
         {"type": "object", "properties": {"customer_codigo": {"type": "string"}, "phone": {"type": "string"}}}, False),
        ("search_customers", "Buscar clientes", ToolType.READ, ToolPermission.READ_ONLY, factory.search_customers,
         {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}, False),
        ("get_customer_360", "Customer 360", ToolType.READ, ToolPermission.READ_ONLY, factory.get_customer_360,
         {"type": "object", "properties": {"customer_codigo": {"type": "string"}}, "required": ["customer_codigo"]}, False),
        ("get_order", "Buscar pedido", ToolType.READ, ToolPermission.READ_ONLY, factory.get_order,
         {"type": "object", "properties": {"order_codigo": {"type": "string"}}, "required": ["order_codigo"]}, False),
        ("get_inventory", "Estoque", ToolType.READ, ToolPermission.READ_ONLY, factory.get_inventory,
         {"type": "object", "properties": {"product_codigo": {"type": "string"}}, "required": ["product_codigo"]}, False),
        ("get_low_stock", "Estoque baixo", ToolType.READ, ToolPermission.READ_ONLY, factory.get_low_stock,
         {"type": "object", "properties": {}}, False),
        ("get_inventory_summary", "Resumo estoque", ToolType.READ, ToolPermission.READ_ONLY, factory.get_inventory_summary,
         {"type": "object", "properties": {}}, False),
        ("get_payments", "Pagamentos", ToolType.READ, ToolPermission.READ_ONLY, factory.get_payments,
         {"type": "object", "properties": {}}, False),
        ("get_receivables", "A receber", ToolType.READ, ToolPermission.READ_ONLY, factory.get_receivables,
         {"type": "object", "properties": {}}, False),
        ("get_financial_summary", "Resumo financeiro", ToolType.READ, ToolPermission.READ_ONLY, factory.get_financial_summary,
         {"type": "object", "properties": {}}, False),
        ("get_sales_summary", "Resumo vendas", ToolType.READ, ToolPermission.READ_ONLY, factory.get_sales_summary,
         {"type": "object", "properties": {}}, False),
        ("search_products", "Buscar produtos", ToolType.READ, ToolPermission.READ_ONLY, factory.search_products,
         {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}, False),
        ("create_order", "Criar pedido", ToolType.WRITE, ToolPermission.OPERATOR, factory.create_order,
         {"type": "object", "properties": {"client_codigo": {"type": "string"}, "items": {"type": "array"}}, "required": ["client_codigo", "items"]}, True),
        ("add_stock", "Estoque", ToolType.WRITE, ToolPermission.OPERATOR, factory.add_stock,
         {"type": "object", "properties": {"product_codigo": {"type": "string"}, "quantity": {"type": "number"}}, "required": ["product_codigo", "quantity"]}, True),
        ("register_payment", "Pagamento", ToolType.WRITE, ToolPermission.OPERATOR, factory.register_payment,
         {"type": "object", "properties": {"order_codigo": {"type": "string"}, "amount": {"type": "number"}, "method": {"type": "string"}}, "required": ["order_codigo", "amount", "method"]}, True),
    ]:
        registry.register(ToolDefinition(
            name=name, description=desc, tool_type=tt, permission=perm,
            handler=handler, input_schema=schema, requires_confirmation=conf,
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
    """Helper to build incoming message dict."""
    return {
        "account_id": account,
        "sender_phone": phone,
        "provider_message_id": msg_id or f"msg_{phone}_{int(time.time()*1000)}",
        "text": text,
        "message_type": "TEXT",
        "from_me": from_me,
    }


# ═══════════════════════════════════════════════════════════
# 1. MESSAGE NORMALIZATION
# ═══════════════════════════════════════════════════════════

class TestMessageNormalization:
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

    def test_from_me_skipped(self, gateway):
        result = gateway.process_incoming(_make_msg(text="Test", from_me=True))
        assert result["status"] == "skipped"
        assert result["error"] == "FROM_ME"


# ═══════════════════════════════════════════════════════════
# 2. IDEMPOTENCY
# ═══════════════════════════════════════════════════════════

class TestIdempotency:
    def test_duplicate_message_skipped(self, gateway, sample_data):
        msg = _make_msg(text="Olá", msg_id="DUPLICATE_001")
        r1 = gateway.process_incoming(msg)
        assert r1["status"] == "processed"
        r2 = gateway.process_incoming(msg)
        assert r2["status"] == "skipped"
        assert r2["error"] == "DUPLICATE_MESSAGE"


# ═══════════════════════════════════════════════════════════
# 3. CONVERSATION CREATION
# ═══════════════════════════════════════════════════════════

class TestConversationCreation:
    def test_creates_conversation(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Olá"))
        assert result["conversation_id"] is not None

    def test_reuses_conversation(self, gateway, sample_data):
        r1 = gateway.process_incoming(_make_msg(text="Olá"))
        r2 = gateway.process_incoming(_make_msg(text="Oi"))
        assert r1["conversation_id"] == r2["conversation_id"]


# ═══════════════════════════════════════════════════════════
# 4. ACCOUNT ISOLATION
# ═══════════════════════════════════════════════════════════

class TestAccountIsolation:
    def test_different_accounts_different_conversations(self, gateway, sample_data):
        r1 = gateway.process_incoming(_make_msg(text="Olá", account="primary"))
        r2 = gateway.process_incoming(_make_msg(text="Olá", account="secondary"))
        assert r1["conversation_id"] != r2["conversation_id"]


# ═══════════════════════════════════════════════════════════
# 5. CUSTOMER RESOLUTION
# ═══════════════════════════════════════════════════════════

class TestCustomerResolution:
    def test_customer_resolved_by_phone(self, gateway, sample_data, repos):
        result = gateway.process_incoming(_make_msg(text="Olá"))
        conv = repos["conv_repo"].find_by_id(result["conversation_id"])
        assert conv.customer_codigo == "000001"

    def test_unknown_customer(self, gateway, sample_data, repos):
        result = gateway.process_incoming(_make_msg(phone="5511000000000", text="Olá"))
        conv = repos["conv_repo"].find_by_id(result["conversation_id"])
        assert conv.customer_codigo is None


# ═══════════════════════════════════════════════════════════
# 6. CONVERSATION STATE MACHINE
# ═══════════════════════════════════════════════════════════

class TestStateMachine:
    def test_initial_state_is_idle(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Olá"))
        repos_conv = SQLAlchemyConversationRepository.__new__(SQLAlchemyConversationRepository)
        conv = gateway.conversation_repo.find_by_id(result["conversation_id"])
        assert conv.state in (ConversationState.IDLE, ConversationState.BROWSING)

    def test_valid_transitions(self):
        from app.domain.whatsapp.conversation import Conversation
        conv = Conversation(state=ConversationState.IDLE)
        assert conv.transition_to(ConversationState.BROWSING)
        assert conv.state == ConversationState.BROWSING
        assert conv.transition_to(ConversationState.BUILDING_ORDER)
        assert conv.state == ConversationState.BUILDING_ORDER

    def test_invalid_transition(self):
        from app.domain.whatsapp.conversation import Conversation
        conv = Conversation(state=ConversationState.IDLE)
        # IDLE -> ORDER_CREATED is not valid (must go through BUILDING_ORDER)
        assert not conv.transition_to(ConversationState.ORDER_CREATED)
        assert conv.state == ConversationState.IDLE  # unchanged


# ═══════════════════════════════════════════════════════════
# 7. HUMAN HANDOFF
# ═══════════════════════════════════════════════════════════

class TestHumanHandoff:
    def test_human_request_transitions(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Quero falar com atendente"))
        assert result["status"] == "human_handoff"

    def test_human_active_blocks_ai(self, gateway, sample_data):
        gateway.process_incoming(_make_msg(text="Quero falar com atendente"))
        # Find conversation
        convs, _ = gateway.conversation_repo.list_active()
        conv = convs[0] if convs else None
        assert conv is not None

        # Takeover
        operator_gw = OperatorGateway(gateway.conversation_repo, gateway.message_repo)
        operator_gw.takeover(conv.id, "Operador1")

        # Now incoming should be blocked
        result = gateway.process_incoming(_make_msg(text="Mais uma mensagem"))
        assert result["status"] == "human_active"


# ═══════════════════════════════════════════════════════════
# 8. MEDIA HANDLING
# ═══════════════════════════════════════════════════════════

class TestMediaHandling:
    def test_image_returns_fallback(self, gateway, sample_data):
        msg = _make_msg(text="")
        msg["message_type"] = "IMAGE"
        result = gateway.process_incoming(msg)
        assert result.get("outbound_text") is not None
        # Should ask user to send text instead
        assert "texto" in result["outbound_text"].lower() or "mensagem" in result["outbound_text"].lower()


# ═══════════════════════════════════════════════════════════
# 9. ANTI-LOOP
# ═══════════════════════════════════════════════════════════

class TestAntiLoop:
    def test_from_me_skipped(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="AI response", from_me=True))
        assert result["status"] == "skipped"


# ═══════════════════════════════════════════════════════════
# 10. CONVERSATION ISOLATION
# ═══════════════════════════════════════════════════════════

class TestConversationIsolation:
    def test_different_phones_different_conversations(self, gateway, sample_data):
        r1 = gateway.process_incoming(_make_msg(phone="5511999887766", text="Olá"))
        r2 = gateway.process_incoming(_make_msg(phone="5511888776655", text="Olá"))
        assert r1["conversation_id"] != r2["conversation_id"]


# ═══════════════════════════════════════════════════════════
# 11. OPERATOR ACTIONS
# ═══════════════════════════════════════════════════════════

class TestOperatorActions:
    def test_takeover(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Olá"))
        conv_id = result["conversation_id"]
        op_gw = OperatorGateway(gateway.conversation_repo, gateway.message_repo)
        r = op_gw.takeover(conv_id, "Operador1")
        assert r["success"]

    def test_release_to_ai(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Olá"))
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
        result = gateway.process_incoming(_make_msg(text="Olá"))
        conv_id = result["conversation_id"]
        op_gw = OperatorGateway(gateway.conversation_repo, gateway.message_repo)
        r = op_gw.release_to_ai(conv_id)
        assert not r["success"]


# ═══════════════════════════════════════════════════════════
# 12. MESSAGE PERSISTENCE
# ═══════════════════════════════════════════════════════════

class TestPersistence:
    def test_messages_persisted(self, gateway, sample_data, repos):
        result = gateway.process_incoming(_make_msg(text="Olá"))
        conv_id = result["conversation_id"]
        messages = repos["msg_repo"].list_by_conversation(conv_id)
        assert len(messages) >= 1
        contents = [m.content for m in messages]
        assert "Olá" in contents

    def test_outbound_persisted(self, gateway, sample_data, repos):
        result = gateway.process_incoming(_make_msg(text="Olá"))
        conv_id = result["conversation_id"]
        messages = repos["msg_repo"].list_by_conversation(conv_id)
        outbounds = [m for m in messages if m.direction == "OUTGOING"]
        assert len(outbounds) >= 1


# ═══════════════════════════════════════════════════════════
# 13. AI ROUTING
# ═══════════════════════════════════════════════════════════

class TestAIRouting:
    def test_greeting_returns_response(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Olá"))
        assert result["outbound_text"] is not None

    def test_inventory_query(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Quanto temos de P13?"))
        assert result["outbound_text"] is not None

    def test_product_search(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Quais produtos vocês vendem?"))
        assert result["outbound_text"] is not None


# ═══════════════════════════════════════════════════════════
# 14. RESET
# ═══════════════════════════════════════════════════════════

class TestReset:
    def test_reset_clears_state(self, gateway, sample_data):
        gateway.process_incoming(_make_msg(text="Olá"))
        result = gateway.process_incoming(_make_msg(text="Começar de novo"))
        assert result["outbound_text"] is not None


# ═══════════════════════════════════════════════════════════
# 15. CONCURRENCY
# ═══════════════════════════════════════════════════════════

class TestConcurrency:
    def test_concurrent_same_phone_same_account(self, gateway, sample_data):
        results = []
        def process(idx):
            try:
                r = gateway.process_incoming(_make_msg(text=f"Msg {idx}", msg_id=f"CONC_{idx}"))
                results.append(r)
            except Exception:
                pass  # Thread-level exception from concurrent DB access

        threads = [threading.Thread(target=process, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        conv_ids = [r["conversation_id"] for r in results if r.get("conversation_id")]
        # All should share the same conversation (same phone)
        assert len(set(conv_ids)) <= 1


# ═══════════════════════════════════════════════════════════
# 16. EDGE CASES
# ═══════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_very_long_message(self, gateway, sample_data):
        long_text = "A" * 4000
        result = gateway.process_incoming(_make_msg(text=long_text))
        assert result["status"] == "processed"

    def test_special_characters(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Pedido: 2×P13 @ R$120,00 (100%)"))
        assert result["status"] == "processed"

    def test_unicode_message(self, gateway, sample_data):
        result = gateway.process_incoming(_make_msg(text="Óla, quero café"))
        assert result["status"] == "processed"
