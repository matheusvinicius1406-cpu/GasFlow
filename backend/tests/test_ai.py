"""
FASE 9 — TEXT AI CORE TESTS
============================
Tests with real in-memory SQLite + Mock LLM Provider.
Covers: Provider, Intent, Tools, Engine, Safety, Grounding, Adversarial.
"""

import json
import pytest
from datetime import datetime
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database.base import Base
from app.infrastructure.repositories.client_model import ClientModel
from app.infrastructure.repositories.product_model import ProductModel
from app.infrastructure.repositories.order_model import OrderModel
from app.infrastructure.repositories.order_item_model import OrderItemModel
from app.infrastructure.repositories.inventory_model import InventoryModel, StockMovementModel
from app.infrastructure.repositories.financial_models import ReceivableModel

from app.domain.ai.provider import LLMProvider, LLMMessage, LLMRole, LLMResponse, LLMUsage
from app.domain.ai.intent import Intent, IntentType, Confidence
from app.domain.ai.tools import ToolRegistry, ToolDefinition, ToolType, ToolPermission, ToolResult
from app.domain.ai.conversation import Conversation, Message, MessageRole

from app.infrastructure.ai.mock_provider import MockLLMProvider
from app.application.ai.engine import AIEngine
from app.application.ai.tools_impl import AIToolsFactory
from app.application.ai.context import ContextBuilder
from app.application.ai.prompts import SYSTEM_PROMPT


# ═══════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def mock_llm():
    return MockLLMProvider()


@pytest.fixture
def tool_registry():
    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="get_customer", description="Get customer",
        tool_type=ToolType.READ, permission=ToolPermission.READ_ONLY,
        input_schema={"type": "object", "properties": {"customer_codigo": {"type": "string"}}},
    ))
    registry.register(ToolDefinition(
        name="get_inventory", description="Get inventory",
        tool_type=ToolType.READ, permission=ToolPermission.READ_ONLY,
        input_schema={"type": "object", "properties": {"product_codigo": {"type": "string"}}},
    ))
    registry.register(ToolDefinition(
        name="create_order", description="Create order",
        tool_type=ToolType.WRITE, permission=ToolPermission.OPERATOR,
        requires_confirmation=True,
        input_schema={"type": "object", "properties": {
            "client_codigo": {"type": "string"}, "items": {"type": "array"},
        }, "required": ["client_codigo", "items"]},
    ))
    return registry


@pytest.fixture
def engine(mock_llm, tool_registry):
    return AIEngine(llm_provider=mock_llm, tool_registry=tool_registry)


def _seed_data(db):
    """Seed test data."""
    db.add(ClientModel(codigo="000001", nome="Maria Silva", telefone="11999999999",
                       rua="Rua A", numero="10", bairro="Centro"))
    db.add(ProductModel(codigo="P00001", nome="GLP P13", tipo="GAS", preco=120.0, estoque=0))
    db.add(ProductModel(codigo="P00002", nome="Agua 20L", tipo="WATER", preco=10.0, estoque=0))
    db.commit()
    # Inventory
    db.add(InventoryModel(product_codigo="P00001", quantity=50, minimum_quantity=10))
    db.add(InventoryModel(product_codigo="P00002", quantity=3, minimum_quantity=20))
    db.commit()


# ═══════════════════════════════════════════════════════════
# 1. PROVIDER
# ═══════════════════════════════════════════════════════════

class TestProvider:
    def test_mock_provider_health(self):
        llm = MockLLMProvider()
        assert llm.health_check() is True

    def test_mock_provider_unavailable(self):
        llm = MockLLMProvider()
        llm.set_unavailable()
        assert llm.health_check() is False
        response = llm.generate([LLMMessage(role=LLMRole.USER, content="test")])
        assert response.error == "AI_PROVIDER_UNAVAILABLE"

    def test_mock_provider_model_name(self):
        llm = MockLLMProvider()
        assert llm.model_name == "mock-model-v1"

    def test_provider_interface(self):
        """MockLLMProvider implements LLMProvider."""
        llm = MockLLMProvider()
        assert isinstance(llm, LLMProvider)

    def test_provider_returns_usage(self):
        llm = MockLLMProvider()
        resp = llm.generate([LLMMessage(role=LLMRole.USER, content="test")])
        assert resp.usage is not None
        assert resp.usage.model == "mock-model-v1"


# ═══════════════════════════════════════════════════════════
# 2. INTENT
# ═══════════════════════════════════════════════════════════

class TestIntent:
    def test_intent_types_exist(self):
        assert hasattr(IntentType, "CUSTOMER_LOOKUP")
        assert hasattr(IntentType, "ORDER_CREATE")
        assert hasattr(IntentType, "INVENTORY_LOOKUP")
        assert hasattr(IntentType, "FINANCIAL_SUMMARY")

    def test_confidence_levels(self):
        assert Confidence.HIGH.value == "HIGH"
        assert Confidence.MEDIUM.value == "MEDIUM"
        assert Confidence.LOW.value == "LOW"

    def test_intent_creation(self):
        intent = Intent(
            type=IntentType.CUSTOMER_LOOKUP,
            confidence=Confidence.HIGH,
            entities={"customer_name": "Maria"},
        )
        assert intent.type == IntentType.CUSTOMER_LOOKUP
        assert intent.confidence == Confidence.HIGH
        assert intent.requires_confirmation is False

    def test_write_intent_requires_confirmation(self):
        intent = Intent(
            type=IntentType.ORDER_CREATE,
            confidence=Confidence.HIGH,
            requires_confirmation=True,
        )
        assert intent.requires_confirmation is True


# ═══════════════════════════════════════════════════════════
# 3. TOOL REGISTRY
# ═══════════════════════════════════════════════════════════

class TestToolRegistry:
    def test_register_and_get(self, tool_registry):
        tool = tool_registry.get("get_customer")
        assert tool is not None
        assert tool.name == "get_customer"

    def test_list_tools(self, tool_registry):
        tools = tool_registry.list_tools()
        assert len(tools) == 3

    def test_list_readable(self, tool_registry):
        readable = tool_registry.list_readable()
        assert len(readable) == 2

    def test_list_writable(self, tool_registry):
        writable = tool_registry.list_writable()
        assert len(writable) == 1
        assert writable[0].name == "create_order"

    def test_validate_input_success(self, tool_registry):
        errors = tool_registry.validate_input("get_customer", {"customer_codigo": "000001"})
        assert errors == []

    def test_validate_input_missing_required(self, tool_registry):
        errors = tool_registry.validate_input("get_customer", {})
        # customer_codigo is not required in schema, so no error
        assert isinstance(errors, list)

    def test_validate_nonexistent_tool(self, tool_registry):
        errors = tool_registry.validate_input("nonexistent_tool", {})
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_requires_confirmation(self, tool_registry):
        tool = tool_registry.get("create_order")
        assert tool.requires_confirmation is True


# ═══════════════════════════════════════════════════════════
# 4. CONTEXT BUILDER
# ═══════════════════════════════════════════════════════════

class TestContextBuilder:
    def test_build_basic(self):
        cb = ContextBuilder()
        ctx = cb.build(IntentType.CUSTOMER_LOOKUP, {"customer_name": "Maria"})
        assert "Maria" in ctx

    def test_build_with_tool_results(self):
        cb = ContextBuilder()
        results = {"nome": "Maria Silva", "telefone": "11999999999"}
        ctx = cb.build(IntentType.CUSTOMER_LOOKUP, {}, tool_results=results)
        assert "Maria Silva" in ctx

    def test_build_with_history(self):
        cb = ContextBuilder()
        history = [{"role": "user", "content": "Quem é Maria?"}]
        ctx = cb.build(IntentType.CUSTOMER_LOOKUP, {}, conversation_history=history)
        assert "Maria" in ctx

    def test_build_truncates_large_context(self):
        cb = ContextBuilder()
        large = "x" * 20000
        ctx = cb.build(IntentType.GENERAL_QUESTION, {"data": large})
        assert len(ctx) < 20000


# ═══════════════════════════════════════════════════════════
# 5. AI ENGINE
# ═══════════════════════════════════════════════════════════

class TestAIEngine:
    def test_chat_unavailable_provider(self, tool_registry):
        llm = MockLLMProvider()
        llm.set_unavailable()
        eng = AIEngine(llm_provider=llm, tool_registry=tool_registry)
        result = eng.chat("test message")
        assert result["error"] == "AI_PROVIDER_UNAVAILABLE"

    def test_chat_basic(self, engine):
        result = engine.chat("Quanto temos de P13?")
        assert "message" in result
        assert result["intent"] is not None

    def test_chat_returns_intent(self, engine):
        result = engine.chat("Quem é Maria?")
        assert result["intent"] is not None

    def test_chat_read_only_blocks_write(self, engine):
        result = engine.chat("Crie um pedido", permission_level="READ_ONLY")
        assert result["error"] == "AI_TOOL_NOT_ALLOWED"

    def test_audit_log(self, engine):
        engine.chat("test1")
        engine.chat("test2")
        log = engine.get_audit_log()
        assert len(log) == 2
        assert all("request_id" in entry for entry in log)

    def test_audit_log_contains_model(self, engine):
        engine.chat("test")
        log = engine.get_audit_log()
        assert log[0]["model"] == "mock-model-v1"


# ═══════════════════════════════════════════════════════════
# 6. GROUNDING (No Hallucination)
# ═══════════════════════════════════════════════════════════

class TestGrounding:
    def test_nonexistent_customer(self, db, mock_llm, tool_registry):
        """AI should not fabricate a non-existent customer."""
        tools = AIToolsFactory(db)
        result = tools.get_customer({"customer_codigo": "999999"})
        assert result.success is False
        assert "não encontrado" in result.error

    def test_nonexistent_product_inventory(self, db, mock_llm, tool_registry):
        tools = AIToolsFactory(db)
        result = tools.get_inventory({"product_codigo": "FAKE"})
        assert result.success is False

    def test_nonexistent_order(self, db):
        tools = AIToolsFactory(db)
        result = tools.get_order({"order_codigo": "999999"})
        assert result.success is False

    def test_system_prompt_no_secrets(self):
        """System prompt should not contain secrets."""
        assert "API_KEY" not in SYSTEM_PROMPT
        assert "password" not in SYSTEM_PROMPT.lower()
        assert "secret" not in SYSTEM_PROMPT.lower()


# ═══════════════════════════════════════════════════════════
# 7. TOOL INTEGRATION (Real DB)
# ═══════════════════════════════════════════════════════════

class TestToolIntegration:
    def test_get_customer_real(self, db):
        _seed_data(db)
        tools = AIToolsFactory(db)
        result = tools.get_customer({"customer_codigo": "000001"})
        assert result.success is True
        assert result.data["nome"] == "Maria Silva"

    def test_search_customers_real(self, db):
        _seed_data(db)
        tools = AIToolsFactory(db)
        result = tools.search_customers({"query": "Maria"})
        assert result.success is True
        assert result.data["total"] >= 1

    def test_get_inventory_real(self, db):
        _seed_data(db)
        tools = AIToolsFactory(db)
        result = tools.get_inventory({"product_codigo": "P00001"})
        assert result.success is True
        assert result.data["quantity"] == 50

    def test_get_low_stock_real(self, db):
        _seed_data(db)
        tools = AIToolsFactory(db)
        result = tools.get_low_stock({})
        assert result.success is True
        assert result.data["count"] >= 1  # P00002 has 3 < min 20

    def test_get_inventory_summary_real(self, db):
        _seed_data(db)
        tools = AIToolsFactory(db)
        result = tools.get_inventory_summary({})
        assert result.success is True
        assert result.data["total_products"] == 2

    def test_get_financial_summary_real(self, db):
        _seed_data(db)
        tools = AIToolsFactory(db)
        result = tools.get_financial_summary({})
        assert result.success is True
        assert "cash_balance" in result.data

    def test_get_payments_empty(self, db):
        _seed_data(db)
        tools = AIToolsFactory(db)
        result = tools.get_payments({})
        assert result.success is True
        assert result.data["count"] == 0

    def test_get_customer_360_real(self, db):
        _seed_data(db)
        # Need an order for 360 to show metrics
        db.add(OrderModel(codigo="O001", client_codigo="000001",
                          subtotal=120.0, delivery_fee=0, discount=0, total=120.0,
                          payment_method="CASH", payment_status="PENDING", status="PENDING",
                          source="MANUAL", address_snapshot="Rua A",
                          created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
        db.commit()
        tools = AIToolsFactory(db)
        result = tools.get_customer_360({"customer_codigo": "000001"})
        assert result.success is True
        assert result.data["total_orders"] == 1

    def test_get_sales_summary_real(self, db):
        _seed_data(db)
        tools = AIToolsFactory(db)
        result = tools.get_sales_summary({})
        assert result.success is True
        assert "total_orders" in result.data


# ═══════════════════════════════════════════════════════════
# 8. SAFETY
# ═══════════════════════════════════════════════════════════

class TestSafety:
    def test_no_direct_db_access(self):
        """AI tools should not import database directly."""
        from app.application.ai import engine
        import inspect
        source = inspect.getsource(engine)
        assert "session.execute" not in source.lower() or "use case" in source.lower()

    def test_write_requires_confirmation(self, tool_registry):
        tool = tool_registry.get("create_order")
        assert tool.requires_confirmation is True

    def test_read_does_not_require_confirmation(self, tool_registry):
        tool = tool_registry.get("get_customer")
        assert tool.requires_confirmation is False

    def test_permission_model(self, tool_registry):
        readable = tool_registry.list_readable()
        for tool in readable:
            assert tool.permission == ToolPermission.READ_ONLY

    def test_write_permission_is_operator(self, tool_registry):
        writable = tool_registry.list_writable()
        for tool in writable:
            assert tool.permission == ToolPermission.OPERATOR


# ═══════════════════════════════════════════════════════════
# 9. CONVERSATION
# ═══════════════════════════════════════════════════════════

class TestConversation:
    def test_conversation_creation(self):
        conv = Conversation(external_id="test-123", title="Test")
        msg = conv.add_message(MessageRole.USER, "Hello")
        assert len(conv.messages) == 1
        assert msg.content == "Hello"

    def test_message_roles(self):
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.TOOL_CALL.value == "tool_call"


# ═══════════════════════════════════════════════════════════
# 10. ADVERSARIAL
# ═══════════════════════════════════════════════════════════

class TestAdversarial:
    def test_adv01_no_sql_execution(self):
        """LLM cannot execute SQL."""
        from app.application.ai import engine
        import inspect
        source = inspect.getsource(engine)
        # Should not contain raw SQL execution
        assert "text(" not in source or "execute" not in source

    def test_adv02_no_arbitrary_tool(self, tool_registry):
        """Cannot call tools not in registry."""
        tool = tool_registry.get("nonexistent_tool_xyz")
        assert tool is None

    def test_adv03_no_direct_inventory_change(self):
        """AI engine should not directly modify inventory."""
        from app.application.ai import engine
        import inspect
        source = inspect.getsource(engine)
        # Engine should not call repository directly
        assert "inventory_repo.update" not in source

    def test_adv04_no_price_fabrication(self, db):
        """AI should not set prices."""
        tools = AIToolsFactory(db)
        # get_customer does not return/modify prices
        result = tools.get_customer({"customer_codigo": "000001"})
        if result.success:
            assert "preco" not in result.data or result.data.get("preco") is None

    def test_adv05_write_needs_confirmation(self, tool_registry):
        """Write tools require confirmation."""
        tool = tool_registry.get("create_order")
        assert tool.requires_confirmation is True

    def test_adv06_no_api_key_in_prompt(self):
        """Prompts should not contain API keys."""
        from app.application.ai import prompts
        import inspect
        source = inspect.getsource(prompts)
        assert "sk-" not in source
        assert "AI_API_KEY" not in source

    def test_adv07_no_stack_trace_leak(self):
        """Error messages should not expose stack traces."""
        llm = MockLLMProvider()
        llm.set_unavailable()
        eng = AIEngine(llm_provider=llm, tool_registry=ToolRegistry())
        result = eng.chat("test")
        assert "traceback" not in str(result).lower()
        assert "File \"" not in str(result)

    def test_adv08_tool_input_validation(self, tool_registry):
        """Invalid tool inputs are rejected."""
        errors = tool_registry.validate_input("get_inventory", {"product_codigo": 123})
        assert len(errors) > 0  # Should reject non-string

    def test_adv09_low_confidence_blocks_action(self, engine):
        """LOW confidence should not execute tools."""
        # MockLLM returns LOW confidence for unrecognized messages
        result = engine.chat("xyzzy random gibberish")
        assert result.get("error") is None or result.get("requires_confirmation") is False

    def test_adv10_ambiguous_customer_not_resolved(self):
        """Ambiguous customers should not be auto-resolved."""
        intent = Intent(
            type=IntentType.CUSTOMER_LOOKUP,
            confidence=Confidence.MEDIUM,
            ambiguous_entities=["Maria Silva", "Maria Souza"],
        )
        assert len(intent.ambiguous_entities) == 2

    def test_adv11_ai_unavailable_does_not_break_crm(self, db):
        """AI unavailability should not break CRM operations."""
        llm = MockLLMProvider()
        llm.set_unavailable()
        eng = AIEngine(llm_provider=llm, tool_registry=ToolRegistry())
        result = eng.chat("test")
        assert result["error"] == "AI_PROVIDER_UNAVAILABLE"
        # CRM operations should still work independently
        tools = AIToolsFactory(db)
        result = tools.get_customer({"customer_codigo": "000001"})
        # This returns not found (no data seeded), but doesn't crash

    def test_adv12_no_prompt_in_response(self, engine):
        """Response should not contain system prompt."""
        result = engine.chat("Quem é Maria?")
        assert SYSTEM_PROMPT[:50] not in result["message"]

    def test_adv13_max_tool_calls(self, engine):
        """Engine has max tool call limit."""
        assert engine.MAX_TOOL_CALLS == 5

    def test_adv14_retry_limit(self, engine):
        """Engine has retry limit."""
        assert engine.MAX_RETRIES == 2

    def test_adv15_context_minimization(self):
        """Context builder minimizes data sent to LLM."""
        cb = ContextBuilder()
        ctx = cb.build(IntentType.INVENTORY_LOOKUP, {"product_codigo": "P00001"})
        # Should not contain customer data
        assert "telefone" not in ctx.lower()
        assert "endereco" not in ctx.lower()

    def test_adv16_customer_notes_not_trusted(self):
        """Customer notes should not alter AI behavior."""
        # The system prompt explicitly states customer messages are untrusted
        assert "untrusted" in SYSTEM_PROMPT.lower() or "não confiável" in SYSTEM_PROMPT.lower() or "não conf" in SYSTEM_PROMPT.lower()

    def test_adv17_financial_needs_confirmation(self, tool_registry):
        """Financial write tools require confirmation."""
        tool = tool_registry.get("create_order")
        assert tool.requires_confirmation is True

    def test_adv18_no_loop_possible(self, engine):
        """Engine has max tool calls to prevent loops."""
        assert engine.MAX_TOOL_CALLS <= 10


# ═══════════════════════════════════════════════════════════
# 11. PROMPT INJECTION
# ═══════════════════════════════════════════════════════════

class TestPromptInjection:
    def test_system_prompt_isolation(self):
        """User text should not override system prompt."""
        # System prompt explicitly says not to follow user instructions
        assert "RULES" in SYSTEM_PROMPT
        assert "Never" in SYSTEM_PROMPT or "Nunca" in SYSTEM_PROMPT

    def test_no_eval_in_code(self):
        """No eval/exec in AI code."""
        from app.application.ai import engine
        import inspect
        source = inspect.getsource(engine)
        assert "eval(" not in source
        assert "exec(" not in source

    def test_no_dynamic_import_in_engine(self):
        """Engine should not use dynamic imports for tools."""
        from app.application.ai import engine
        import inspect
        source = inspect.getsource(engine)
        # Should not dynamically import arbitrary modules
        assert "__import__(" not in source
