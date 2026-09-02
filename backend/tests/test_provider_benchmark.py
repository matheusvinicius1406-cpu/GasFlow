"""
Provider Benchmark Harness — WAVE 2.5

Measures real performance of WhatsApp provider adapters.
Runs WITHOUT a live WhatsApp connection (unit-level benchmarks).
Live benchmarks require services to be running.

Usage:
    pytest tests/test_provider_benchmark.py -v
"""

import pytest
import asyncio
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.whatsapp_provider.models import (
    WhatsAppContact, ConnectionInfo, SendOptions, SendResult,
    ConnectionState, ProviderType, MediaType, WhatsAppEvent,
)
from app.domain.whatsapp_provider.contract import WhatsAppProvider
from app.domain.whatsapp_provider.session import WhatsAppSessionManager
from app.domain.whatsapp_provider.errors import (
    WhatsAppError, WhatsAppConnectionError, WhatsAppSendError,
    WhatsAppAuthError, WhatsAppRateLimitError,
)
from app.domain.whatsapp_provider.retry import RetryPolicy
from app.infrastructure.whatsapp_provider.factory import create_provider


# ── Mock Provider for Benchmarking ──────────────────────

class MockProvider(WhatsAppProvider):
    """Mock provider for benchmark testing."""

    def __init__(self, account_id: str = "test", latency_ms: int = 50):
        self._account_id = account_id
        self._connected = False
        self._latency_ms = latency_ms

    @property
    def provider_type(self): return ProviderType.CURRENT
    @property
    def account_id(self): return self._account_id

    async def start(self):
        await asyncio.sleep(self._latency_ms / 1000)
        self._connected = True

    async def stop(self):
        self._connected = False

    async def logout(self):
        self._connected = False

    async def get_connection_state(self):
        return ConnectionState.CONNECTED if self._connected else ConnectionState.DISCONNECTED

    async def get_connection_info(self):
        return ConnectionInfo(
            connected=self._connected,
            provider_type=self.provider_type,
        )

    def is_connected(self):
        return self._connected

    async def get_qr_code(self):
        return "mock_qr_code" if not self._connected else None

    async def send_text(self, options: SendOptions) -> SendResult:
        await asyncio.sleep(self._latency_ms / 1000)
        return SendResult(
            success=True,
            message_id=f"mock_{int(time.time()*1000)}",
            provider=self.provider_type,
        )

    async def send_media(self, options: SendOptions) -> SendResult:
        await asyncio.sleep(self._latency_ms / 1000)
        return SendResult(success=True, message_id="mock_media", provider=self.provider_type)

    async def send_typing(self, recipient: str) -> bool:
        return True

    async def mark_as_read(self, message_id: str) -> bool:
        return True

    async def get_contacts(self) -> list:
        return [
            WhatsAppContact(jid="5511999999999@c.us", phone="5511999999999", name="Test Contact"),
        ]

    async def get_contact(self, jid: str):
        return WhatsAppContact(jid=jid, name="Test")

    async def get_session_info(self):
        return {"account_id": self._account_id, "connected": self._connected}


# ── Benchmark Tests ─────────────────────────────────────

class TestProviderFactory:
    """Benchmark: provider creation time."""

    def test_create_current_adapter(self):
        start = time.perf_counter()
        provider = create_provider("primary", "current")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert provider.provider_type == ProviderType.CURRENT
        assert elapsed_ms < 200  # Should be near-instant (cold import may add latency)

    def test_create_evolution_adapter(self):
        start = time.perf_counter()
        provider = create_provider("primary", "evolution")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert provider.provider_type == ProviderType.EVOLUTION
        assert elapsed_ms < 100

    def test_create_baileys_adapter(self):
        start = time.perf_counter()
        provider = create_provider("primary", "baileys")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert provider.provider_type == ProviderType.BAILEYS
        assert elapsed_ms < 100


class TestProviderLatency:
    """Benchmark: mock provider latency."""

    def test_send_text_latency(self):
        provider = MockProvider(latency_ms=10)
        options = SendOptions(recipient="5511999999999", text="Test message")

        async def bench():
            await provider.start()
            start = time.perf_counter()
            result = await provider.send_text(options)
            elapsed_ms = (time.perf_counter() - start) * 1000
            return result, elapsed_ms

        result, elapsed_ms = asyncio.run(bench())
        assert result.success is True
        assert elapsed_ms < 200  # Should be fast for mock

    def test_connection_latency(self):
        provider = MockProvider(latency_ms=5)

        async def bench():
            start = time.perf_counter()
            await provider.start()
            elapsed_ms = (time.perf_counter() - start) * 1000
            state = await provider.get_connection_state()
            return state, elapsed_ms

        state, elapsed_ms = asyncio.run(bench())
        assert state == ConnectionState.CONNECTED
        assert elapsed_ms < 100


class TestRetryPerformance:
    """Benchmark: retry policy performance."""

    def test_retry_with_success(self):
        policy = RetryPolicy(max_retries=3, base_delay_ms=10)
        call_count = 0

        async def op():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise WhatsAppConnectionError("temporary")
            return "ok"

        start = time.perf_counter()
        result = asyncio.run(policy.execute_with_retry(op))
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert result == "ok"
        assert call_count == 3
        assert elapsed_ms < 500  # Should be fast with 10ms delays

    def test_retry_no_delay_on_success(self):
        policy = RetryPolicy(max_retries=3, base_delay_ms=100)

        async def op():
            return "immediate"

        start = time.perf_counter()
        result = asyncio.run(policy.execute_with_retry(op))
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert result == "immediate"
        assert elapsed_ms < 50  # No delay on first success


class TestSessionManagerPerformance:
    """Benchmark: session manager operations."""

    def test_register_multiple_providers(self):
        mgr = WhatsAppSessionManager()
        providers = [MockProvider(f"account_{i}") for i in range(10)]

        start = time.perf_counter()
        for i, p in enumerate(providers):
            mgr.register_provider(f"account_{i}", p)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert mgr.get_provider_count() == 10
        assert elapsed_ms < 50

    def test_get_all_status(self):
        mgr = WhatsAppSessionManager()
        for i in range(5):
            mgr.register_provider(f"account_{i}", MockProvider(f"account_{i}"))

        async def bench():
            start = time.perf_counter()
            statuses = await mgr.get_all_status()
            elapsed_ms = (time.perf_counter() - start) * 1000
            return statuses, elapsed_ms

        statuses, elapsed_ms = asyncio.run(bench())
        assert len(statuses) == 5
        assert elapsed_ms < 500


# ── Contract Compliance Tests ───────────────────────────

class TestContractCompliance:
    """Verify all adapters comply with the contract."""

    def test_current_adapter_implements_contract(self):
        from app.infrastructure.whatsapp_provider.current_adapter import WhatsAppWebAdapter
        provider = WhatsAppWebAdapter("primary")
        assert isinstance(provider, WhatsAppProvider)
        assert provider.provider_type == ProviderType.CURRENT

    def test_evolution_adapter_implements_contract(self):
        from app.infrastructure.whatsapp_provider.evolution_adapter import EvolutionAdapter
        provider = EvolutionAdapter("primary")
        assert isinstance(provider, WhatsAppProvider)
        assert provider.provider_type == ProviderType.EVOLUTION

    def test_baileys_adapter_implements_contract(self):
        from app.infrastructure.whatsapp_provider.baileys_adapter import BaileysAdapter
        provider = BaileysAdapter("primary")
        assert isinstance(provider, WhatsAppProvider)
        assert provider.provider_type == ProviderType.BAILEYS

    def test_all_adapters_have_required_methods(self):
        """Every adapter must implement all abstract methods."""
        adapters = [
            ("current", "primary"),
            ("evolution", "primary"),
            ("baileys", "primary"),
        ]
        for ptype, account in adapters:
            provider = create_provider(account, ptype)
            # Check all required methods exist
            assert hasattr(provider, 'start')
            assert hasattr(provider, 'stop')
            assert hasattr(provider, 'logout')
            assert hasattr(provider, 'get_connection_state')
            assert hasattr(provider, 'get_connection_info')
            assert hasattr(provider, 'is_connected')
            assert hasattr(provider, 'get_qr_code')
            assert hasattr(provider, 'send_text')
            assert hasattr(provider, 'send_media')
            assert hasattr(provider, 'send_typing')
            assert hasattr(provider, 'mark_as_read')
            assert hasattr(provider, 'get_contacts')
            assert hasattr(provider, 'get_contact')
            assert hasattr(provider, 'get_session_info')
            assert hasattr(provider, 'health_check')


# ── Model Performance ───────────────────────────────────

class TestModelPerformance:
    """Benchmark: model serialization/deserialization."""

    def test_contact_serialization(self):
        contact = WhatsAppContact(
            jid="5511999999999@c.us",
            phone="5511999999999",
            name="João Silva",
            push_name="João",
            business_name="João Gás",
            is_business=False,
            is_group=False,
        )

        start = time.perf_counter()
        for _ in range(1000):
            d = contact.to_dict()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert d["jid"] == "5511999999999@c.us"
        assert elapsed_ms < 100  # 1000 serializations in <100ms

    def test_send_result_serialization(self):
        result = SendResult(
            success=True,
            message_id="msg_123",
            provider=ProviderType.CURRENT,
        )

        start = time.perf_counter()
        for _ in range(1000):
            d = result.to_dict()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert d["success"] is True
        assert elapsed_ms < 100

    def test_event_serialization(self):
        event = WhatsAppEvent(
            event_type="message.received",
            account_id="primary",
            provider_type=ProviderType.CURRENT,
            data={"text": "Hello", "sender": "5511999999999"},
        )

        start = time.perf_counter()
        for _ in range(1000):
            d = event.to_dict()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert d["event_type"] == "message.received"
        assert elapsed_ms < 100
