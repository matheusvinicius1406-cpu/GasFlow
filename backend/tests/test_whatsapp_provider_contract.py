"""
WhatsApp Provider Contract Tests — WAVE 2

Shared test suite that validates any WhatsAppProvider implementation.
Tests: models, contract, session, retry, errors, factory, normalization.

These tests run WITHOUT a real WhatsApp connection.
"""

import pytest
from datetime import datetime
from app.domain.whatsapp_provider.models import (
    WhatsAppContact, ConnectionInfo, SendResult,
    WhatsAppEvent, ConnectionState, ProviderType, MediaType, MessageStatus,
)
from app.domain.whatsapp_provider.contract import WhatsAppProvider
from app.domain.whatsapp_provider.session import WhatsAppSessionManager
from app.domain.whatsapp_provider.errors import (
    WhatsAppError, WhatsAppErrorType, WhatsAppConnectionError,
    WhatsAppSendError, WhatsAppAuthError, WhatsAppRateLimitError,
)
from app.domain.whatsapp_provider.retry import RetryPolicy


# ── Model Tests ─────────────────────────────────────────

class TestWhatsAppContact:
    def test_creation(self):
        c = WhatsAppContact(jid="5511999999999@c.us", phone="5511999999999", name="João")
        assert c.jid == "5511999999999@c.us"
        assert c.phone == "5511999999999"
        assert c.is_group is False

    def test_to_dict(self):
        c = WhatsAppContact(jid="test@g.us", is_group=True)
        d = c.to_dict()
        assert d["jid"] == "test@g.us"
        assert d["is_group"] is True


class TestConnectionState:
    def test_all_states(self):
        states = [s.value for s in ConnectionState]
        assert "disconnected" in states
        assert "connected" in states
        assert "qr_pending" in states
        assert "connecting" in states
        assert "reconnecting" in states
        assert "auth_failed" in states


class TestProviderType:
    def test_all_types(self):
        types = [t.value for t in ProviderType]
        assert "current" in types
        assert "evolution" in types
        assert "baileys" in types
        assert "meta" in types


class TestMessageStatus:
    def test_all_statuses(self):
        statuses = [s.value for s in MessageStatus]
        assert "pending" in statuses
        assert "sent" in statuses
        assert "delivered" in statuses
        assert "read" in statuses
        assert "failed" in statuses


# ── SendResult Tests ────────────────────────────────────

class TestSendResult:
    def test_success(self):
        r = SendResult(success=True, message_id="msg_123", provider=ProviderType.CURRENT)
        d = r.to_dict()
        assert d["success"] is True
        assert d["message_id"] == "msg_123"

    def test_failure(self):
        r = SendResult(success=False, error="Not connected", error_code="NOT_CONNECTED")
        d = r.to_dict()
        assert d["success"] is False
        assert d["error_code"] == "NOT_CONNECTED"


# ── ConnectionInfo Tests ────────────────────────────────

class TestConnectionInfo:
    def test_default(self):
        info = ConnectionInfo()
        assert info.connected is False
        assert info.phone is None

    def test_connected(self):
        info = ConnectionInfo(
            connected=True,
            phone="5511999999999",
            provider_type=ProviderType.CURRENT,
        )
        d = info.to_dict()
        assert d["connected"] is True
        assert d["phone"] == "5511999999999"
        assert d["provider_type"] == "current"


# ── Error Tests ─────────────────────────────────────────

class TestErrors:
    def test_base_error(self):
        e = WhatsAppError("test error", WhatsAppErrorType.UNKNOWN)
        assert str(e) == "test error"
        assert e.error_type == WhatsAppErrorType.UNKNOWN
        assert e.retryable is False

    def test_connection_error_retryable(self):
        e = WhatsAppConnectionError("connection failed")
        assert e.retryable is True
        assert e.error_type == WhatsAppErrorType.CONNECTION_ERROR

    def test_auth_error_not_retryable(self):
        e = WhatsAppAuthError("auth failed")
        assert e.retryable is False

    def test_rate_limit_error(self):
        e = WhatsAppRateLimitError("rate limited", retry_after=120)
        assert e.retryable is True
        assert e.retry_after == 120

    def test_to_dict(self):
        e = WhatsAppSendError("send failed", provider="evolution")
        d = e.to_dict()
        assert d["error_type"] == "send_error"
        assert d["provider"] == "evolution"


# ── Retry Tests ─────────────────────────────────────────

class TestRetryPolicy:
    def test_success_no_retry(self):
        policy = RetryPolicy(max_retries=3)
        call_count = 0

        async def success_op():
            nonlocal call_count
            call_count += 1
            return "ok"

        import asyncio
        result = asyncio.run(policy.execute_with_retry(success_op))
        assert result == "ok"
        assert call_count == 1
        assert policy.get_metrics()["total_successes"] == 1

    def test_retry_on_temporary_failure(self):
        policy = RetryPolicy(max_retries=2, base_delay_ms=10)
        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise WhatsAppConnectionError("temporary")
            return "ok"

        import asyncio
        result = asyncio.run(policy.execute_with_retry(fail_then_succeed))
        assert result == "ok"
        assert call_count == 3

    def test_permanent_failure_no_retry(self):
        policy = RetryPolicy(max_retries=3)
        call_count = 0

        async def permanent_fail():
            nonlocal call_count
            call_count += 1
            raise WhatsAppAuthError("permanent")

        import asyncio
        with pytest.raises(WhatsAppAuthError):
            asyncio.run(policy.execute_with_retry(permanent_fail))
        assert call_count == 1  # No retry for permanent failures

    def test_all_retries_exhausted(self):
        policy = RetryPolicy(max_retries=2, base_delay_ms=10)

        async def always_fail():
            raise WhatsAppConnectionError("always fails")

        import asyncio
        with pytest.raises(WhatsAppConnectionError):
            asyncio.run(policy.execute_with_retry(always_fail))
        assert policy.get_metrics()["total_failures"] == 1

    def test_metrics(self):
        policy = RetryPolicy(max_retries=1, base_delay_ms=10)
        metrics = policy.get_metrics()
        assert "total_attempts" in metrics
        assert "total_retries" in metrics
        assert "total_successes" in metrics
        assert "total_failures" in metrics


# ── Session Manager Tests ───────────────────────────────

class TestSessionManager:
    def test_register_provider(self):
        mgr = WhatsAppSessionManager()

        class MockProvider(WhatsAppProvider):
            @property
            def provider_type(self): return ProviderType.CURRENT
            @property
            def account_id(self): return "test"
            async def start(self): pass
            async def stop(self): pass
            async def logout(self): pass
            async def get_connection_state(self): return ConnectionState.DISCONNECTED
            async def get_connection_info(self): return ConnectionInfo()
            def is_connected(self): return False
            async def get_qr_code(self): return None
            async def send_text(self, opts): return SendResult(success=False)
            async def send_media(self, opts): return SendResult(success=False)
            async def send_typing(self, r): return False
            async def mark_as_read(self, m): return False
            async def get_contacts(self): return []
            async def get_contact(self, j): return None
            async def get_session_info(self): return {}

        provider = MockProvider()
        mgr.register_provider("primary", provider)
        assert mgr.get_provider_count() == 1
        assert mgr.get_provider("primary") is provider

    def test_get_nonexistent_provider(self):
        mgr = WhatsAppSessionManager()
        assert mgr.get_provider("nonexistent") is None


# ── Factory Tests ───────────────────────────────────────

class TestFactory:
    def test_create_current(self):
        from app.infrastructure.whatsapp_provider.factory import create_provider
        provider = create_provider("primary", "current")
        assert provider.provider_type == ProviderType.CURRENT
        assert provider.account_id == "primary"

    def test_create_evolution(self):
        from app.infrastructure.whatsapp_provider.factory import create_provider
        provider = create_provider("primary", "evolution")
        assert provider.provider_type == ProviderType.EVOLUTION

    def test_create_baileys(self):
        from app.infrastructure.whatsapp_provider.factory import create_provider
        provider = create_provider("primary", "baileys")
        assert provider.provider_type == ProviderType.BAILEYS

    def test_unknown_falls_back_to_current(self):
        from app.infrastructure.whatsapp_provider.factory import create_provider
        provider = create_provider("primary", "unknown")
        assert provider.provider_type == ProviderType.CURRENT


# ── Event Normalization Tests ───────────────────────────

class TestEventNormalization:
    def test_event_creation(self):
        event = WhatsAppEvent(
            event_type="message.received",
            account_id="primary",
            provider_type=ProviderType.CURRENT,
            data={"text": "Hello"},
        )
        d = event.to_dict()
        assert d["event_type"] == "message.received"
        assert d["account_id"] == "primary"
        assert d["data"]["text"] == "Hello"

    def test_event_with_timestamp(self):
        now = datetime.utcnow()
        event = WhatsAppEvent(
            event_type="connection.changed",
            account_id="primary",
            provider_type=ProviderType.EVOLUTION,
            timestamp=now,
        )
        d = event.to_dict()
        assert d["timestamp"] is not None


# ── MediaType Tests ─────────────────────────────────────

class TestMediaType:
    def test_all_types(self):
        types = [t.value for t in MediaType]
        assert "text" in types
        assert "image" in types
        assert "audio" in types
        assert "video" in types
        assert "document" in types
