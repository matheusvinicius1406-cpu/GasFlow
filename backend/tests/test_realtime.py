"""RT-01 — Tests for the realtime WebSocket layer.

Covers:
- ConnectionManager: connect/disconnect, per-channel broadcast isolation,
  dead-connection cleanup, stats.
- Event → channel routing (broadcast_event): tenant / delivery / driver /
  operations channels.
- /ws endpoint: invalid token rejected (4001), tenant mismatch rejected
  (4003), valid token receives welcome and answers ping with pong.

The module had zero tests before RT-01; these are deterministic (no real
Redis/network) and use the in-memory event bus.
"""

import json
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.domain.events.event_bus import DomainEvent, EventType
from app.infrastructure.realtime.websocket import (
    ConnectionManager,
    get_ws_manager,
)


# ── Fake WebSocket for unit tests ────────────────────────

class FakeWS:
    """Minimal WebSocket stand-in recording sends."""

    def __init__(self, conn_id: int = 0):
        self.conn_id = conn_id
        self.accepted = False
        self.sent: list[str] = []
        self.closed = False

    async def accept(self):
        self.accepted = True

    async def send_text(self, message: str):
        self.sent.append(message)

    def __hash__(self):
        return hash(("fakews", self.conn_id))


# ── ConnectionManager unit tests ────────────────────────

@pytest.mark.asyncio
async def test_connect_and_disconnect_manage_channels():
    manager = ConnectionManager()
    ws = FakeWS(1)

    await manager.connect(ws, "tenant:t1", {"user_id": "u1"})

    assert ws.accepted is True
    assert len(manager._channels["tenant:t1"]) == 1
    assert manager.get_stats()["total_connections"] == 1

    manager.disconnect(ws)

    assert manager.get_stats()["total_connections"] == 0
    assert "tenant:t1" not in manager._channels


@pytest.mark.asyncio
async def test_broadcast_is_isolated_per_channel():
    manager = ConnectionManager()
    ws_t1 = FakeWS(1)
    ws_t2 = FakeWS(2)
    await manager.connect(ws_t1, "tenant:t1", {})
    await manager.connect(ws_t2, "tenant:t2", {})

    await manager.broadcast_to_channel("tenant:t1", {"type": "event", "k": "v"})

    assert len(ws_t1.sent) == 1
    assert json.loads(ws_t1.sent[0])["k"] == "v"
    assert ws_t2.sent == []  # t2 must not receive t1 events


@pytest.mark.asyncio
async def test_broadcast_drops_dead_connections():
    manager = ConnectionManager()
    ws = FakeWS(1)
    await manager.connect(ws, "tenant:t1", {})

    # Simulate a broken connection: send_text raises
    async def boom(message: str):
        raise RuntimeError("gone")

    ws.send_text = boom  # type: ignore[method-assign]

    await manager.broadcast_to_channel("tenant:t1", {"type": "event"})

    # Dead connection removed, channel cleaned up
    assert manager.get_stats()["total_connections"] == 0
    assert "tenant:t1" not in manager._channels


@pytest.mark.asyncio
async def test_broadcast_to_channel_with_no_connections_is_noop():
    manager = ConnectionManager()
    await manager.broadcast_to_channel("tenant:empty", {"type": "event"})
    assert manager.get_stats()["total_events_sent"] == 0


# ── Event → channel routing ─────────────────────────────

@pytest.mark.asyncio
async def test_delivery_event_routes_to_tenant_and_delivery_channels():
    manager = ConnectionManager()
    ws_tenant = FakeWS(1)
    ws_delivery = FakeWS(2)
    await manager.connect(ws_tenant, "tenant:t1", {})
    await manager.connect(ws_delivery, "delivery:d1", {})

    event = DomainEvent(
        type=EventType.DELIVERY_STARTED,
        tenant_id="t1",
        aggregate_id="d1",
        data={"driver_id": "drv1"},
    )
    await manager.broadcast_event(event)

    tenant_msgs = [json.loads(m) for m in ws_tenant.sent]
    delivery_msgs = [json.loads(m) for m in ws_delivery.sent]

    assert tenant_msgs[0]["event"]["type"] == "delivery.started"
    assert delivery_msgs[0]["event"]["aggregate_id"] == "d1"


@pytest.mark.asyncio
async def test_driver_location_event_routes_to_operations_channel():
    manager = ConnectionManager()
    ws_ops = FakeWS(1)
    ws_tenant = FakeWS(2)
    await manager.connect(ws_ops, "operations:t1", {})
    await manager.connect(ws_tenant, "tenant:t1", {})

    event = DomainEvent(
        type=EventType.DRIVER_LOCATION_UPDATED,
        tenant_id="t1",
        aggregate_id="drv1",
        data={"driver_id": "drv1"},
    )
    await manager.broadcast_event(event)

    ops_msgs = [json.loads(m) for m in ws_ops.sent]
    tenant_msgs = [json.loads(m) for m in ws_tenant.sent]

    # Location goes to tenant channel (dashboard) + operations channel
    assert ops_msgs[0]["event"]["type"] == "driver.location_updated"
    assert tenant_msgs[0]["event"]["type"] == "driver.location_updated"


@pytest.mark.asyncio
async def test_unrelated_event_goes_only_to_tenant_channel():
    manager = ConnectionManager()
    ws_tenant = FakeWS(1)
    await manager.connect(ws_tenant, "tenant:t1", {})

    event = DomainEvent(
        type=EventType.DELIVERY_CREATED,
        tenant_id="t1",
        aggregate_id="d1",
    )
    await manager.broadcast_event(event)

    assert len(ws_tenant.sent) == 1


# ── /ws endpoint tests (via TestClient) ─────────────────

@pytest.fixture(scope="module")
def client():
    with TestClient(app := __import__("app.main", fromlist=["app"]).app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    res = client.post("/auth/login", json={
        "username": "admin",
        "password": "test_password_123",
    })
    assert res.status_code == 200
    return res.json()["token"]


def test_ws_rejects_invalid_token(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws?token=invalid-token"):
            pass
    assert exc.value.code == 4001


def test_ws_welcome_and_pong(client, admin_token):
    with client.websocket_connect(f"/ws?token={admin_token}") as ws:
        welcome = ws.receive_json()
        assert welcome["type"] == "connected"
        assert welcome["channel"].startswith("tenant:")

        ws.send_text("ping")
        pong = ws.receive_json()
        assert pong == {"type": "pong"}


def test_ws_rejects_channel_from_other_tenant(client, admin_token):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"/ws?token={admin_token}&channel=tenant:other-tenant"
        ):
            pass
    assert exc.value.code == 4003


def test_realtime_stats_endpoint(client):
    res = client.get("/realtime/stats")
    assert res.status_code == 200
    body = res.json()
    assert "total_connections" in body
    assert "channels" in body


def test_bridge_subscribes_delivery_and_driver_events(monkeypatch):
    """setup_realtime_bridge() subscribes the WS bridge to delivery/driver events.

    Deterministic version of the end-to-end path: we assert the wiring
    (bus subscription) rather than crossing event loops between the sync
    test thread and the TestClient's async portal.
    """
    import app.infrastructure.realtime.websocket as ws_module
    from app.domain.events.event_bus import EventBus

    bus = EventBus()
    monkeypatch.setattr(ws_module, "get_event_bus", lambda: bus)

    ws_module.setup_realtime_bridge()

    subscribed = set(bus._handlers.keys())
    # The WS bridge is the only subscriber after a fresh setup
    assert EventType.DELIVERY_STARTED in subscribed
    assert EventType.DELIVERY_COMPLETED in subscribed
    assert EventType.DRIVER_AVAILABLE in subscribed
    assert EventType.DRIVER_LOCATION_UPDATED in subscribed
    # Order events (RT-01 pendência) are bridged too
    assert EventType.ORDER_CREATED in subscribed
    assert EventType.ORDER_UPDATED in subscribed
    # Unrelated events are NOT bridged to WS
    assert EventType.PAYMENT_CONFIRMED not in subscribed


def test_manager_singleton_is_shared():
    assert get_ws_manager() is get_ws_manager()
