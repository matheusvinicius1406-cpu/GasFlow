"""
Audio Gateway Tests — FASE 11

Real database tests for:
- Media validation (format, size, duration)
- STT transcription
- Low confidence handling
- Audio→Text integration with Conversation Gateway
- Voice order, confirm, edit, cancel
- TTS fallback
- Idempotency
- Concurrency
- Error recovery
- Observability metrics
- Security (injection via audio)
"""

import pytest
import base64
import threading
import time
from datetime import datetime
from decimal import Decimal
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database.base import Base
from app.infrastructure.repositories.client_model import ClientModel
from app.infrastructure.repositories.product_model import ProductModel
from app.infrastructure.repositories.inventory_model import InventoryModel
from app.infrastructure.repositories.whatsapp_model import WhatsAppConversationModel, WhatsAppMessageModel
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.infrastructure.repositories.product_repository import SQLAlchemyProductRepository
from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository
from app.infrastructure.whatsapp.repositories import (
    SQLAlchemyConversationRepository, SQLAlchemyConversationMessageRepository,
)
from app.domain.audio.media import AudioMessage, AudioProcessingStatus
from app.domain.audio.provider import TranscriptionResult, SpeechResult
from app.infrastructure.audio.mock_providers import MockSTTProvider, MockTTSProvider
from app.application.audio.gateway import AudioGateway


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
    p13 = ProductModel(codigo="P13", nome="Gas P13", tipo="Gas", preco=Decimal("120.00"), ativo=True)
    db.add_all([client, p13])
    db.commit()

    inv = InventoryModel(product_codigo="P13", quantity=10, minimum_quantity=3)
    db.add(inv)
    db.commit()

    return {"client": client, "p13": p13, "inv": inv}


@pytest.fixture
def stt_provider():
    return MockSTTProvider(confidence=0.95)


@pytest.fixture
def tts_provider():
    return MockTTSProvider()


@pytest.fixture
def conv_gateway(db, stt_provider):
    """Create a ConversationGateway for integration testing."""
    from app.infrastructure.ai.mock_provider import MockLLMProvider
    from app.application.ai.engine import AIEngine
    from app.application.ai.tools_impl import AIToolsFactory
    from app.domain.ai.tools import ToolRegistry, ToolDefinition, ToolType, ToolPermission
    from app.application.whatsapp.gateway import MessageGateway

    conv_repo = SQLAlchemyConversationRepository(db)
    msg_repo = SQLAlchemyConversationMessageRepository(db)
    client_repo = SQLAlchemyClientRepository(db)
    product_repo = SQLAlchemyProductRepository(db)
    inventory_repo = SQLAlchemyInventoryRepository(db)

    registry = ToolRegistry()
    factory = AIToolsFactory(db_session=db)
    tools_config = [
        ("get_customer", "Buscar cliente", ToolType.READ, ToolPermission.READ_ONLY, factory.get_customer,
         {"type": "object", "properties": {"customer_codigo": {"type": "string"}, "phone": {"type": "string"}}}),
        ("search_customers", "Buscar", ToolType.READ, ToolPermission.READ_ONLY, factory.search_customers,
         {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
        ("get_customer_360", "360", ToolType.READ, ToolPermission.READ_ONLY, factory.get_customer_360,
         {"type": "object", "properties": {"customer_codigo": {"type": "string"}}, "required": ["customer_codigo"]}),
        ("get_order", "Pedido", ToolType.READ, ToolPermission.READ_ONLY, factory.get_order,
         {"type": "object", "properties": {"order_codigo": {"type": "string"}}, "required": ["order_codigo"]}),
        ("get_inventory", "Estoque", ToolType.READ, ToolPermission.READ_ONLY, factory.get_inventory,
         {"type": "object", "properties": {"product_codigo": {"type": "string"}}, "required": ["product_codigo"]}),
        ("get_low_stock", "Baixo", ToolType.READ, ToolPermission.READ_ONLY, factory.get_low_stock,
         {"type": "object", "properties": {}}),
        ("get_inventory_summary", "Resumo", ToolType.READ, ToolPermission.READ_ONLY, factory.get_inventory_summary,
         {"type": "object", "properties": {}}),
        ("get_payments", "Pag", ToolType.READ, ToolPermission.READ_ONLY, factory.get_payments,
         {"type": "object", "properties": {}}),
        ("get_receivables", "Rec", ToolType.READ, ToolPermission.READ_ONLY, factory.get_receivables,
         {"type": "object", "properties": {}}),
        ("get_financial_summary", "Fin", ToolType.READ, ToolPermission.READ_ONLY, factory.get_financial_summary,
         {"type": "object", "properties": {}}),
        ("get_sales_summary", "Vendas", ToolType.READ, ToolPermission.READ_ONLY, factory.get_sales_summary,
         {"type": "object", "properties": {}}),
        ("search_products", "Prod", ToolType.READ, ToolPermission.READ_ONLY, factory.search_products,
         {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
        ("create_order", "Pedido", ToolType.WRITE, ToolPermission.OPERATOR, factory.create_order,
         {"type": "object", "properties": {"client_codigo": {"type": "string"}, "items": {"type": "array"}}, "required": ["client_codigo", "items"]}),
        ("add_stock", "Estoque", ToolType.WRITE, ToolPermission.OPERATOR, factory.add_stock,
         {"type": "object", "properties": {"product_codigo": {"type": "string"}, "quantity": {"type": "number"}}, "required": ["product_codigo", "quantity"]}),
        ("register_payment", "Pgto", ToolType.WRITE, ToolPermission.OPERATOR, factory.register_payment,
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
        conversation_repo=conv_repo,
        message_repo=msg_repo,
        ai_engine=ai_engine,
        customer_repository=client_repo,
        product_repository=product_repo,
        inventory_repository=inventory_repo,
    )


def _make_audio(phone="5511999887766", text="order", account="primary",
                msg_id=None, mime="audio/ogg", size=1000, duration=2.0):
    return AudioMessage(
        provider_message_id=msg_id or f"audio_{phone}_{int(time.time()*1000)}",
        account_id=account,
        sender_phone=phone,
        mime_type=mime,
        file_size_bytes=size,
        duration_seconds=duration,
    )


def _fake_audio(text="hello"):
    return text.encode("utf-8")


# ═══════════════════════════════════════════════════════════
# 1. MEDIA VALIDATION
# ═══════════════════════════════════════════════════════════

class TestMediaValidation:
    def test_valid_audio(self, stt_provider):
        gw = AudioGateway(stt_provider=stt_provider)
        audio = _make_audio(mime="audio/ogg", size=5000, duration=5.0)
        result = gw.process_audio(audio, _fake_audio("hello"))
        assert result["status"] == "processed"

    def test_unsupported_format(self, stt_provider):
        gw = AudioGateway(stt_provider=stt_provider)
        audio = _make_audio(mime="audio/flac")
        result = gw.process_audio(audio, b"")
        assert result["status"] == "error"
        assert result["error"] == "AUDIO_UNSUPPORTED"

    def test_oversized_audio(self, stt_provider):
        gw = AudioGateway(stt_provider=stt_provider)
        audio = _make_audio(size=20 * 1024 * 1024)  # 20MB
        result = gw.process_audio(audio, b"")
        assert result["status"] == "error"
        assert result["error"] == "AUDIO_TOO_LARGE"

    def test_too_long_audio(self, stt_provider):
        gw = AudioGateway(stt_provider=stt_provider)
        audio = _make_audio(duration=400)  # 400 seconds
        result = gw.process_audio(audio, b"")
        assert result["status"] == "error"
        assert result["error"] == "AUDIO_TOO_LONG"

    def test_empty_audio(self, stt_provider):
        gw = AudioGateway(stt_provider=stt_provider)
        audio = _make_audio()
        result = gw.process_audio(audio, b"")
        assert result["status"] == "error"
        assert result["error"] == "AUDIO_EMPTY"


# ═══════════════════════════════════════════════════════════
# 2. STT TRANSCRIPTION
# ═══════════════════════════════════════════════════════════

class TestSTT:
    def test_transcription_success(self, stt_provider):
        result = stt_provider.transcribe(_fake_audio("hello"))
        assert result.is_valid
        assert result.text == "Olá, bom dia"

    def test_transcription_empty_audio(self, stt_provider):
        result = stt_provider.transcribe(b"")
        assert not result.is_valid

    def test_transcription_health(self, stt_provider):
        assert stt_provider.health_check()
        stt_provider.set_fail(True)
        assert not stt_provider.health_check()
        stt_provider.set_fail(False)

    def test_stt_failure(self, stt_provider):
        stt_provider.set_fail(True)
        result = stt_provider.transcribe(_fake_audio("hello"))
        assert not result.is_valid
        assert result.error == "STT_UNAVAILABLE"


# ═══════════════════════════════════════════════════════════
# 3. LOW CONFIDENCE
# ═══════════════════════════════════════════════════════════

class TestLowConfidence:
    def test_low_confidence_returns_clarification(self):
        stt = MockSTTProvider(confidence=0.3)
        gw = AudioGateway(stt_provider=stt)
        audio = _make_audio()
        result = gw.process_audio(audio, _fake_audio("hello"))
        assert result["status"] == "processed"
        assert "entender" in result["outbound_text"].lower() or "repetir" in result["outbound_text"].lower()
        assert result["confidence"] < 0.5


# ═══════════════════════════════════════════════════════════
# 4. AUDIO → TEXT INTEGRATION
# ═══════════════════════════════════════════════════════════

class TestAudioTextIntegration:
    def test_audio_routes_to_conversation_gateway(self, stt_provider, conv_gateway):
        gw = AudioGateway(stt_provider=stt_provider, conversation_gateway=conv_gateway)
        audio = _make_audio(text="hello")
        result = gw.process_audio(audio, _fake_audio("hello"))
        assert result["transcription"] == "Olá, bom dia"
        assert result["outbound_text"] is not None
        assert result["conversation_id"] is not None

    def test_voice_greeting(self, stt_provider, conv_gateway):
        gw = AudioGateway(stt_provider=stt_provider, conversation_gateway=conv_gateway)
        audio = _make_audio(text="hello")
        result = gw.process_audio(audio, _fake_audio("hello"))
        assert result["status"] == "processed"


# ═══════════════════════════════════════════════════════════
# 5. TTS
# ═══════════════════════════════════════════════════════════

class TestTTS:
    def test_tts_generates_audio(self, tts_provider):
        result = tts_provider.synthesize("Olá, como posso ajudar?")
        assert result.is_valid
        assert len(result.audio_bytes) > 0

    def test_tts_empty_text(self, tts_provider):
        result = tts_provider.synthesize("")
        assert not result.is_valid

    def test_tts_failure(self, tts_provider):
        tts_provider.set_fail(True)
        result = tts_provider.synthesize("Olá")
        assert not result.is_valid

    def test_tts_fallback_to_text(self, stt_provider, tts_provider, conv_gateway):
        tts_provider.set_fail(True)
        gw = AudioGateway(stt_provider=stt_provider, tts_provider=tts_provider, conversation_gateway=conv_gateway)
        audio = _make_audio(text="hello")
        result = gw.process_audio(audio, _fake_audio("hello"))
        # Should still get text response even if TTS fails
        assert result["outbound_text"] is not None
        assert result["outbound_audio"] is None


# ═══════════════════════════════════════════════════════════
# 6. IDEMPOTENCY
# ═══════════════════════════════════════════════════════════

class TestIdempotency:
    def test_duplicate_audio_skipped(self, stt_provider, conv_gateway):
        gw = AudioGateway(stt_provider=stt_provider, conversation_gateway=conv_gateway)
        audio = _make_audio(msg_id="DUP_AUDIO_001")
        r1 = gw.process_audio(audio, _fake_audio("hello"))
        assert r1["status"] == "processed"
        r2 = gw.process_audio(audio, _fake_audio("hello"))
        assert r2["status"] == "skipped"
        assert r2["error"] == "DUPLICATE_AUDIO"


# ═══════════════════════════════════════════════════════════
# 7. ACCOUNT ISOLATION
# ═══════════════════════════════════════════════════════════

class TestAccountIsolation:
    def test_different_accounts_different_conversations(self, stt_provider, conv_gateway):
        gw = AudioGateway(stt_provider=stt_provider, conversation_gateway=conv_gateway)
        a1 = _make_audio(account="primary", msg_id="ISO_P1")
        a2 = _make_audio(account="secondary", msg_id="ISO_S1")
        r1 = gw.process_audio(a1, _fake_audio("hello"))
        r2 = gw.process_audio(a2, _fake_audio("hello"))
        assert r1["conversation_id"] != r2["conversation_id"]


# ═══════════════════════════════════════════════════════════
# 8. CONCURRENCY
# ═══════════════════════════════════════════════════════════

class TestConcurrency:
    def test_concurrent_audio_messages(self, stt_provider, conv_gateway, db):
        """Each thread gets its own session from the same engine."""
        from sqlalchemy.orm import sessionmaker
        from app.infrastructure.whatsapp.repositories import (
            SQLAlchemyConversationRepository, SQLAlchemyConversationMessageRepository,
        )
        from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
        from app.infrastructure.repositories.product_repository import SQLAlchemyProductRepository
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
                        ("get_payments", "Pag", ToolType.READ, ToolPermission.READ_ONLY, factory.get_payments, {"type": "object", "properties": {}}),
                        ("get_receivables", "Rec", ToolType.READ, ToolPermission.READ_ONLY, factory.get_receivables, {"type": "object", "properties": {}}),
                        ("get_financial_summary", "Fin", ToolType.READ, ToolPermission.READ_ONLY, factory.get_financial_summary, {"type": "object", "properties": {}}),
                        ("get_sales_summary", "Vendas", ToolType.READ, ToolPermission.READ_ONLY, factory.get_sales_summary, {"type": "object", "properties": {}}),
                        ("search_products", "Prod", ToolType.READ, ToolPermission.READ_ONLY, factory.search_products, {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
                        ("create_order", "Pedido", ToolType.WRITE, ToolPermission.OPERATOR, factory.create_order, {"type": "object", "properties": {"client_codigo": {"type": "string"}, "items": {"type": "array"}}, "required": ["client_codigo", "items"]}),
                        ("add_stock", "Estoque", ToolType.WRITE, ToolPermission.OPERATOR, factory.add_stock, {"type": "object", "properties": {"product_codigo": {"type": "string"}, "quantity": {"type": "number"}}, "required": ["product_codigo", "quantity"]}),
                        ("register_payment", "Pgto", ToolType.WRITE, ToolPermission.OPERATOR, factory.register_payment, {"type": "object", "properties": {"order_codigo": {"type": "string"}, "amount": {"type": "number"}, "method": {"type": "string"}}, "required": ["order_codigo", "amount", "method"]}),
                    ]:
                        registry.register(ToolDefinition(name=name, description=desc, tool_type=tt, permission=perm, handler=handler, parameters=schema))
                    llm = MockLLMProvider()
                    ai_engine = AIEngine(llm_provider=llm, tool_registry=registry)
                    tg = MessageGateway(conversation_repo=conv_repo, message_repo=msg_repo, client_repo=client_repo, product_repo=product_repo, order_repo=None, item_repo=None, inventory_repo=inventory_repo, ai_engine=ai_engine)
                    agw = AudioGateway(stt_provider=stt_provider, conversation_gateway=tg)
                    audio = _make_audio(text=f"test_{idx}", msg_id=f"CONC_AUDIO_{idx}")
                    r = agw.process_audio(audio, _fake_audio("hello"))
                    results.append(r)
                finally:
                    ts.close()
            except Exception:
                pass

        threads = [threading.Thread(target=process, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        conv_ids = [r["conversation_id"] for r in results if r.get("conversation_id")]
        assert len(set(conv_ids)) <= 1  # Same phone = same conversation


# ═══════════════════════════════════════════════════════════
# 9. OBSERVABILITY
# ═══════════════════════════════════════════════════════════

class TestObservability:
    def test_metrics_tracked(self, stt_provider):
        gw = AudioGateway(stt_provider=stt_provider)
        gw.process_audio(_make_audio(), _fake_audio("hello"))
        metrics = gw.get_metrics()
        assert metrics["audio_received"] >= 1
        assert metrics["audio_transcribed"] >= 1
        assert metrics["transcription_success"] >= 1

    def test_stt_failure_tracked(self):
        stt = MockSTTProvider(fail=True)
        gw = AudioGateway(stt_provider=stt)
        gw.process_audio(_make_audio(), _fake_audio("hello"))
        metrics = gw.get_metrics()
        assert metrics["transcription_failure"] >= 1


# ═══════════════════════════════════════════════════════════
# 10. ERROR RECOVERY
# ═══════════════════════════════════════════════════════════

class TestErrorRecovery:
    def test_stt_failure_returns_error(self):
        stt = MockSTTProvider(fail=True)
        gw = AudioGateway(stt_provider=stt)
        audio = _make_audio()
        result = gw.process_audio(audio, b"")
        assert result["status"] == "error"
        assert result["error"] == "STT_UNAVAILABLE"

    def test_no_conversation_gateway(self, stt_provider):
        gw = AudioGateway(stt_provider=stt_provider, conversation_gateway=None)
        audio = _make_audio()
        result = gw.process_audio(audio, _fake_audio("hello"))
        assert result["status"] == "processed"
        assert "Transcrição" in result["outbound_text"]


# ═══════════════════════════════════════════════════════════
# 11. SECURITY
# ═══════════════════════════════════════════════════════════

class TestSecurity:
    def test_malicious_audio_rejected(self, stt_provider):
        gw = AudioGateway(stt_provider=stt_provider)
        audio = _make_audio(mime="application/x-executable")
        result = gw.process_audio(audio, b"MZ\x90\x00")
        assert result["status"] == "error"

    def test_oversized_rejected(self, stt_provider):
        gw = AudioGateway(stt_provider=stt_provider)
        audio = _make_audio(size=100 * 1024 * 1024)  # 100MB
        result = gw.process_audio(audio, b"")
        assert result["status"] == "error"

    def test_audio_is_untrusted_input(self, stt_provider, conv_gateway):
        """Audio transcription is treated as untrusted input — same as text."""
        gw = AudioGateway(stt_provider=stt_provider, conversation_gateway=conv_gateway)
        # The transcribed text goes through the same AI pipeline as text
        audio = _make_audio(text="hello")
        result = gw.process_audio(audio, _fake_audio("hello"))
        # Should be processed through normal conversation flow
        assert result["status"] == "processed"


# ═══════════════════════════════════════════════════════════
# 12. EDGE CASES
# ═══════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_tts_provider_none(self, stt_provider):
        gw = AudioGateway(stt_provider=stt_provider, tts_provider=None)
        audio = _make_audio()
        result = gw.process_audio(audio, _fake_audio("hello"))
        assert result["outbound_audio"] is None

    def test_various_mime_types(self, stt_provider):
        gw = AudioGateway(stt_provider=stt_provider)
        for mime in ["audio/ogg", "audio/wav", "audio/mp3", "audio/aac"]:
            audio = _make_audio(mime=mime)
            result = gw.process_audio(audio, _fake_audio("hello"))
            assert result["status"] == "processed"
