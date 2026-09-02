"""
Real Live Provider Tests — WAVE 2.6

Tests the actual WhatsApp adapter against the running Node.js service.
No mocking — real HTTP calls to localhost:3000.

Prerequisites:
- WhatsApp Node.js service running on localhost:3000

Usage:
    pytest tests/test_provider_live_real.py -v
"""

import pytest
import asyncio
import time
import httpx
from datetime import datetime

from app.infrastructure.whatsapp_provider.current_adapter import WhatsAppWebAdapter
from app.domain.whatsapp_provider.models import (
    ConnectionState, ProviderType, SendOptions,
)


# ── Check if service is running ────────────────────────

def is_whatsapp_service_running() -> bool:
    """Check if WhatsApp Node.js service is available."""
    try:
        resp = httpx.get("http://localhost:3000/api/health", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


SERVICE_AVAILABLE = is_whatsapp_service_running()
pytestmark = pytest.mark.skipif(
    not SERVICE_AVAILABLE,
    reason="WhatsApp service not running on localhost:3000"
)


# ── Health & Status Tests ──────────────────────────────

class TestLiveHealth:
    """Real health checks against running service."""

    def test_health_endpoint(self):
        """Health endpoint returns valid response."""
        resp = httpx.get("http://localhost:3000/api/health", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "uptimeSeconds" in data
        assert "memory" in data
        assert "whatsapp" in data
        print(f"\nHEALTH: uptime={data['uptimeSeconds']}s, "
              f"RSS={data['memory']['rssMb']}MB, "
              f"heap={data['memory']['heapUsedMb']}MB")

    def test_accounts_endpoint(self):
        """Accounts endpoint returns both accounts."""
        resp = httpx.get("http://localhost:3000/api/whatsapp/accounts", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        accounts = data.get("accounts", [])
        assert len(accounts) == 2
        ids = [a["id"] for a in accounts]
        assert "primary" in ids
        assert "secondary" in ids
        print(f"\nACCOUNTS: {ids}")

    def test_account_status_structure(self):
        """Account status has expected structure."""
        resp = httpx.get("http://localhost:3000/api/whatsapp/accounts", timeout=5)
        data = resp.json()
        for acc in data["accounts"]:
            assert "id" in acc
            assert "name" in acc
            assert "status" in acc
            assert "state" in acc["status"]
            assert "connected" in acc["status"]
            assert acc["status"]["state"] in (
                "disconnected", "connecting", "qr_pending", "connected"
            )


# ── Adapter Tests ──────────────────────────────────────

class TestLiveAdapter:
    """Test the WhatsAppWebAdapter against real service."""

    def test_adapter_creation(self):
        """Adapter can be created."""
        adapter = WhatsAppWebAdapter("primary")
        assert adapter.provider_type == ProviderType.CURRENT
        assert adapter.account_id == "primary"

    def test_adapter_connection_state(self):
        """Adapter reports connection state."""
        adapter = WhatsAppWebAdapter("primary")
        state = asyncio.run(adapter.get_connection_state())
        assert state in (ConnectionState.DISCONNECTED, ConnectionState.CONNECTED)
        print(f"\nSTATE: {state.value}")

    def test_adapter_connection_info(self):
        """Adapter returns connection info."""
        adapter = WhatsAppWebAdapter("primary")
        info = asyncio.run(adapter.get_connection_info())
        assert info is not None
        assert info.provider_type == ProviderType.CURRENT
        print(f"\nINFO: connected={info.connected}, phone={info.phone}")

    def test_adapter_health_check(self):
        """Adapter health check works."""
        adapter = WhatsAppWebAdapter("primary")
        healthy = asyncio.run(adapter.health_check())
        # Health check returns whether account is connected
        # Since account is disconnected, health_check returns False
        assert isinstance(healthy, bool)
        print(f"\nHEALTH: {healthy}")

    def test_adapter_session_info(self):
        """Adapter returns session info."""
        adapter = WhatsAppWebAdapter("primary")
        info = asyncio.run(adapter.get_session_info())
        assert "account_id" in info
        assert info["account_id"] == "primary"
        assert "provider" in info
        print(f"\nSESSION: {info}")

    def test_adapter_send_when_disconnected(self):
        """Send fails gracefully when disconnected."""
        adapter = WhatsAppWebAdapter("primary")
        options = SendOptions(
            recipient="5511999999999",
            text="Test message",
        )
        result = asyncio.run(adapter.send_text(options))
        assert result.success is False
        assert result.error_code == "NOT_CONNECTED"
        print(f"\nSEND (disconnected): {result.to_dict()}")


# ── Multi-Account Tests ────────────────────────────────

class TestLiveMultiAccount:
    """Test multi-account isolation."""

    def test_both_accounts_visible(self):
        """Both accounts are visible."""
        adapter_p = WhatsAppWebAdapter("primary")
        adapter_s = WhatsAppWebAdapter("secondary")

        info_p = asyncio.run(adapter_p.get_connection_info())
        info_s = asyncio.run(adapter_s.get_connection_info())

        assert info_p.provider_type == ProviderType.CURRENT
        assert info_s.provider_type == ProviderType.CURRENT
        print(f"\nPRIMARY: connected={info_p.connected}")
        print(f"SECONDARY: connected={info_s.connected}")

    def test_account_isolation(self):
        """Accounts are independent."""
        adapter_p = WhatsAppWebAdapter("primary")
        adapter_s = WhatsAppWebAdapter("secondary")

        state_p = asyncio.run(adapter_p.get_connection_state())
        state_s = asyncio.run(adapter_s.get_connection_state())

        # Both should be disconnected (no QR scanned)
        # But they should be independent
        assert state_p == ConnectionState.DISCONNECTED
        assert state_s == ConnectionState.DISCONNECTED
        print(f"\nISOLATION: primary={state_p.value}, secondary={state_s.value}")


# ── Performance Measurement ────────────────────────────

class TestLivePerformance:
    """Measure real performance metrics."""

    def test_adapter_creation_time(self):
        """Measure adapter creation time."""
        times = []
        for _ in range(100):
            start = time.perf_counter()
            adapter = WhatsAppWebAdapter("primary")
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg = sum(times) / len(times)
        print(f"\nADAPTER CREATE: avg={avg:.2f}ms, min={min(times):.2f}ms, max={max(times):.2f}ms")

    def test_health_check_latency(self):
        """Measure health check latency."""
        adapter = WhatsAppWebAdapter("primary")
        times = []
        for _ in range(10):
            start = time.perf_counter()
            asyncio.run(adapter.health_check())
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg = sum(times) / len(times)
        p95 = sorted(times)[int(len(times) * 0.95)]
        print(f"\nHEALTH LATENCY: avg={avg:.2f}ms, p95={p95:.2f}ms")

    def test_connection_state_latency(self):
        """Measure connection state query latency."""
        adapter = WhatsAppWebAdapter("primary")
        times = []
        for _ in range(10):
            start = time.perf_counter()
            asyncio.run(adapter.get_connection_state())
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg = sum(times) / len(times)
        print(f"\nSTATE LATENCY: avg={avg:.2f}ms")

    def test_accounts_list_latency(self):
        """Measure accounts list latency."""
        times = []
        for _ in range(10):
            start = time.perf_counter()
            resp = httpx.get("http://localhost:3000/api/whatsapp/accounts", timeout=5)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg = sum(times) / len(times)
        p95 = sorted(times)[int(len(times) * 0.95)]
        print(f"\nACCOUNTS LATENCY: avg={avg:.2f}ms, p95={p95:.2f}ms")
