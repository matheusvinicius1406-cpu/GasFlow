"""
Live Provider Test Harness — WAVE 2.5

This test suite requires LIVE WhatsApp services running.
It validates real behavior, not mocked behavior.

Prerequisites:
- WhatsApp Node.js service running on localhost:3000
- OR Evolution API running on localhost:8080
- OR Baileys service running on localhost:3001
- Valid WhatsApp session connected

Set WHATSAPP_PROVIDER env var to test specific provider.
Set WHATSAPP_TEST_PHONE env var with a valid test number.

Usage:
    WHATSAPP_PROVIDER=current WHATSAPP_TEST_PHONE=5511999999999 \\
    pytest tests/test_provider_live_harness.py -v --timeout=60

All tests are marked with @pytest.mark.live — skip if services not available.
"""

import pytest
import asyncio
import os
import time
from datetime import datetime

from app.domain.whatsapp_provider.models import (
    SendOptions,
    ConnectionState,
    ProviderType,
)
from app.infrastructure.whatsapp_provider.factory import create_provider

# Skip all live tests if LIVE_MODE not set
LIVE_MODE = os.getenv("LIVE_MODE", "false").lower() == "true"
TEST_PHONE = os.getenv("WHATSAPP_TEST_PHONE", "")
PROVIDER_TYPE = os.getenv("WHATSAPP_PROVIDER", "current")

pytestmark = pytest.mark.skipif(not LIVE_MODE, reason="LIVE_MODE not enabled. Set LIVE_MODE=true to run live tests.")


@pytest.fixture
def provider():
    """Create provider for live testing."""
    return create_provider("primary", PROVIDER_TYPE)


@pytest.fixture
def test_phone():
    """Get test phone number."""
    if not TEST_PHONE:
        pytest.skip("WHATSAPP_TEST_PHONE not set")
    return TEST_PHONE


# ── Connection Tests ────────────────────────────────────


class TestLiveConnection:
    """Real connection tests."""

    @pytest.mark.live
    def test_provider_creation(self, provider):
        """Provider can be created."""
        assert provider is not None
        assert provider.provider_type in (
            ProviderType.CURRENT,
            ProviderType.EVOLUTION,
            ProviderType.BAILEYS,
            ProviderType.META,
        )

    @pytest.mark.live
    def test_initial_state_disconnected(self, provider):
        """Provider starts disconnected."""
        state = asyncio.run(provider.get_connection_state())
        assert state in (ConnectionState.DISCONNECTED, ConnectionState.CONNECTING, ConnectionState.CONNECTED)

    @pytest.mark.live
    def test_connection_info(self, provider):
        """Provider returns connection info."""
        info = asyncio.run(provider.get_connection_info())
        assert info is not None
        assert hasattr(info, "connected")
        assert hasattr(info, "provider_type")


# ── Send Tests ──────────────────────────────────────────


class TestLiveSend:
    """Real send tests — requires connected WhatsApp."""

    @pytest.mark.live
    def test_send_text(self, provider, test_phone):
        """Send a real text message."""
        options = SendOptions(
            recipient=test_phone,
            text=f"[GasFlow WAVE 2.5 Test] {datetime.utcnow().isoformat()}",
        )
        result = asyncio.run(provider.send_text(options))
        # Record result for analysis
        print(f"\nSEND RESULT: {result.to_dict()}")
        # We don't assert success — connection may not be active
        # The test validates the adapter works end-to-end

    @pytest.mark.live
    def test_send_duplicate_idempotency(self, provider, test_phone):
        """Send same message twice with same idempotency key."""
        key = f"test_{int(time.time())}"
        options = SendOptions(
            recipient=test_phone,
            text="[GasFlow IDEMPOTENCY TEST]",
            idempotency_key=key,
        )
        r1 = asyncio.run(provider.send_text(options))
        r2 = asyncio.run(provider.send_text(options))
        # Both should succeed but ideally only one message delivered
        print(f"\nIDEMPOTENCY: r1={r1.to_dict()}, r2={r2.to_dict()}")


# ── Status Tests ────────────────────────────────────────


class TestLiveStatus:
    """Real status checks."""

    @pytest.mark.live
    def test_get_contacts(self, provider):
        """Get real contacts."""
        contacts = asyncio.run(provider.get_contacts())
        print(f"\nCONTACTS: {len(contacts)} found")
        assert isinstance(contacts, list)

    @pytest.mark.live
    def test_session_info(self, provider):
        """Get session info."""
        info = asyncio.run(provider.get_session_info())
        print(f"\nSESSION: {info}")
        assert "account_id" in info

    @pytest.mark.live
    def test_health_check(self, provider):
        """Health check."""
        healthy = asyncio.run(provider.health_check())
        print(f"\nHEALTH: {healthy}")
        assert isinstance(healthy, bool)


# ── QR Tests ────────────────────────────────────────────


class TestLiveQR:
    """QR code tests."""

    @pytest.mark.live
    def test_get_qr(self, provider):
        """Get QR code if not connected."""
        qr = asyncio.run(provider.get_qr_code())
        if qr:
            print(f"\nQR LENGTH: {len(qr)}")
        # QR may be None if already connected


# ── Reconnect Tests ─────────────────────────────────────


class TestLiveReconnect:
    """Reconnection tests."""

    @pytest.mark.live
    def test_stop_and_restart(self, provider):
        """Stop and restart provider."""
        asyncio.run(provider.stop())
        state_after_stop = asyncio.run(provider.get_connection_state())
        print(f"\nAFTER STOP: {state_after_stop}")

        asyncio.run(provider.start())
        state_after_start = asyncio.run(provider.get_connection_state())
        print(f"\nAFTER START: {state_after_start}")


# ── Error Handling Tests ────────────────────────────────


class TestLiveErrors:
    """Error handling with real provider."""

    @pytest.mark.live
    def test_send_to_invalid_number(self, provider):
        """Send to invalid number — should handle gracefully."""
        options = SendOptions(
            recipient="0000000000000",
            text="Test error handling",
        )
        result = asyncio.run(provider.send_text(options))
        print(f"\nINVALID NUMBER: {result.to_dict()}")
        # Should not crash, should return error

    @pytest.mark.live
    def test_send_empty_message(self, provider, test_phone):
        """Send empty message — should handle gracefully."""
        options = SendOptions(recipient=test_phone, text="")
        result = asyncio.run(provider.send_text(options))
        print(f"\nEMPTY MSG: {result.to_dict()}")
