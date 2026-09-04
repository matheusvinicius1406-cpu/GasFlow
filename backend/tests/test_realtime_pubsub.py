"""RT-01 (pendência) — Redis pub/sub cross-worker propagation tests.

Deterministic: exercises RedisPubSub against a fake async redis client and
the ConnectionManager routing against fake WebSockets — no real Redis/network.

Covers:
- publish_event: envelope carries origin + event, malformed payloads dropped.
- is_own_message: worker skips its own published events (avoids duplicates).
- decode_message: rejects non-message payloads.
- broadcast_event with pubsub enabled: publishes cross-worker AND routes
  locally; foreign events (broadcast_event_dict) route to local channels only.
"""

import json

import pytest

from app.domain.events.event_bus import DomainEvent, EventType
from app.infrastructure.realtime.websocket import ConnectionManager
from app.infrastructure.realtime.pubsub import RedisPubSub, EVENTS_CHANNEL


class FakeAsyncRedis:
    """Minimal async redis stand-in recording publishes."""

    def __init__(self):
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str):
        self.published.append((channel, message))
        return 1


class FakeClient:
    def __init__(self):
        self.redis = FakeAsyncRedis()

    def from_url(self, *args, **kwargs):
        return self.redis


class FakeWS:
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


@pytest.fixture
def pubsub(monkeypatch) -> RedisPubSub:
    fake = FakeClient()
    monkeypatch.setattr("redis.asyncio.from_url", fake.from_url)
    ps = RedisPubSub(url="redis://fake:6379/0", worker_id="worker-A")
    return ps


# ── RedisPubSub ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_event_envelope_has_origin_and_event(pubsub):
    event_data = {"type": "event", "event": {"type": "order.created"}}
    await pubsub.publish_event(event_data)

    assert len(pubsub._client.published) == 1  # type: ignore[attr-defined]
    channel, raw = pubsub._client.published[0]  # type: ignore[attr-defined]
    assert channel == EVENTS_CHANNEL
    body = json.loads(raw)
    assert body["origin"] == "worker-A"
    assert body["event"] == event_data


@pytest.mark.asyncio
async def test_publish_event_fails_open_when_redis_down(monkeypatch, pubsub):
    class ExplodingRedis:
        async def publish(self, channel, message):
            raise ConnectionError("refused")

    class ExplodingClient:
        def from_url(self, *args, **kwargs):
            return ExplodingRedis()

    monkeypatch.setattr("redis.asyncio.from_url", ExplodingClient().from_url)
    # Must not raise — propagation is best-effort.
    await pubsub.publish_event({"type": "event", "event": {}})


def test_decode_message_parses_envelope():
    body = json.dumps({"origin": "worker-B", "event": {"type": "x"}})
    data = RedisPubSub.decode_message(body)
    assert data == {"origin": "worker-B", "event": {"type": "x"}}


def test_decode_message_rejects_malformed():
    assert RedisPubSub.decode_message("not-json") is None
    assert RedisPubSub.decode_message(json.dumps({"origin": "w"})) is None
    assert RedisPubSub.decode_message(json.dumps([])) is None
    assert RedisPubSub.decode_message(None) is None


def test_is_own_message_skips_self(pubsub):
    assert pubsub.is_own_message({"origin": "worker-A"}) is True
    assert pubsub.is_own_message({"origin": "worker-B"}) is False


# ── ConnectionManager + pubsub ──────────────────────────

@pytest.mark.asyncio
async def test_broadcast_event_publishes_and_routes_locally(pubsub):
    manager = ConnectionManager()
    manager.enable_pubsub(pubsub)
    ws = FakeWS(1)
    await manager.connect(ws, "tenant:t1", {})

    event = DomainEvent(
        type=EventType.ORDER_CREATED,
        tenant_id="t1",
        aggregate_id="000001",
        data={"codigo": "000001", "status": "PENDING"},
    )
    await manager.broadcast_event(event)

    # Local client received it on the tenant channel.
    assert len(ws.sent) == 1
    received = json.loads(ws.sent[0])
    assert received["event"]["type"] == "order.created"

    # Cross-worker: published exactly once with this worker as origin.
    published = pubsub._client.published  # type: ignore[attr-defined]
    assert len(published) == 1
    assert json.loads(published[0][1])["origin"] == "worker-A"


@pytest.mark.asyncio
async def test_remote_event_routes_to_local_channels_only(pubsub):
    """A foreign worker's event (via broadcast_event_dict) is routed locally
    but NOT re-published to Redis (no loops)."""
    manager = ConnectionManager()
    manager.enable_pubsub(pubsub)
    ws = FakeWS(1)
    await manager.connect(ws, "tenant:t2", {})

    remote = {
        "type": "event",
        "event": {
            "type": "delivery.completed",
            "tenant_id": "t2",
            "aggregate_id": "DLV-1",
            "data": {},
        },
    }
    await manager.broadcast_event_dict(remote)

    assert len(ws.sent) == 1
    assert json.loads(ws.sent[0])["event"]["type"] == "delivery.completed"
    # No cross-worker publish for foreign events (no loops) — the client was
    # never even created lazily.
    assert pubsub._client is None


@pytest.mark.asyncio
async def test_manager_without_pubsub_does_not_publish():
    manager = ConnectionManager()
    ws = FakeWS(1)
    await manager.connect(ws, "tenant:t1", {})

    event = DomainEvent(type=EventType.DELIVERY_STARTED, tenant_id="t1")
    await manager.broadcast_event(event)

    assert len(ws.sent) == 1
