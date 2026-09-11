"""
WebSocket Realtime — Event Bus → WebSocket Manager

Architecture:
    Domain Event → Event Bus → WebSocket Manager → Connected Clients

Channels:
    tenant:{tenant_id}    → admin clients
    driver:{driver_id}    → driver app clients
    delivery:{delivery_id}→ delivery watchers

Authentication:
    Token required on connect. Tenant/role derived from token.
    No anonymous connections to operational data.
"""

import json
import asyncio
import logging
from typing import TYPE_CHECKING, Dict, Set, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from datetime import datetime

from app.domain.events.event_bus import get_event_bus, EventType, DomainEvent

if TYPE_CHECKING:
    from app.infrastructure.realtime.pubsub import RedisPubSub

logger = logging.getLogger("gasflow.realtime")

router = APIRouter(tags=["realtime"])


class ConnectionManager:
    """
    Manages WebSocket connections and channels.

    Thread-safe via asyncio event loop (single-threaded).
    For multi-process, use Redis pub/sub (future enhancement).
    """

    def __init__(self):
        # channel_name → set of WebSocket connections
        self._channels: Dict[str, Set[WebSocket]] = {}
        # connection_id → metadata
        self._connections: Dict[str, dict] = {}
        # Stats
        self._total_connected = 0
        self._total_events_sent = 0
        # Optional cross-worker transport (Redis pub/sub). When set, every
        # broadcast is also published so other uvicorn workers can relay it
        # to their own clients (see app/infrastructure/realtime/pubsub.py).
        self._pubsub: Optional["RedisPubSub"] = None

    def enable_pubsub(self, pubsub: "RedisPubSub"):
        """Enable cross-worker propagation via Redis pub/sub."""
        self._pubsub = pubsub

    async def connect(self, websocket: WebSocket, channel: str, metadata: dict):
        """Accept and register a WebSocket connection."""
        await websocket.accept()

        conn_id = id(websocket)
        if channel not in self._channels:
            self._channels[channel] = set()
        self._channels[channel].add(websocket)
        self._connections[conn_id] = {
            "channel": channel,
            "metadata": metadata,
            "connected_at": datetime.utcnow().isoformat(),
        }
        self._total_connected += 1
        logger.info(f"WS connected: channel={channel}, meta={metadata}")

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        conn_id = id(websocket)
        info = self._connections.pop(conn_id, {})
        channel = info.get("channel", "")
        if channel in self._channels:
            self._channels[channel].discard(websocket)
            if not self._channels[channel]:
                del self._channels[channel]
        logger.info(f"WS disconnected: channel={channel}")

    async def broadcast_to_channel(self, channel: str, event_data: dict):
        """Send an event to all connections in a channel."""
        connections = self._channels.get(channel, set())
        if not connections:
            return

        message = json.dumps(event_data, default=str)
        dead = []
        for ws in connections:
            try:
                await ws.send_text(message)
                self._total_events_sent += 1
            except Exception:
                logger.debug("ws.broadcast_send_failed — connection marked dead", exc_info=True)
                dead.append(ws)

        # Clean up dead connections
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_event(self, event: DomainEvent):
        """Route an Event Bus event locally and (if enabled) cross-worker."""
        event_data = {
            "type": "event",
            "event": event.to_dict(),
        }

        # Propagate to other workers first so clients connected to them get
        # the event promptly even if a local channel is slow.
        if self._pubsub is not None:
            await self._pubsub.publish_event(event_data)

        await self._route_event(event_data)

    async def broadcast_event_dict(self, event_data: dict):
        """Route a remote (other-worker) event to local channels only."""
        await self._route_event(event_data)

    async def _route_event(self, event_data: dict):
        """Route an event envelope to the local WebSocket channels."""
        event = event_data.get("event") or {}
        event_type = str(event.get("type", ""))
        tenant_id = str(event.get("tenant_id", ""))
        aggregate_id = str(event.get("aggregate_id", ""))
        data = event.get("data") or {}

        # 1. Tenant channel (admin dashboard)
        if tenant_id:
            await self.broadcast_to_channel(f"tenant:{tenant_id}", event_data)

        # 2. Delivery channel (if delivery-related)
        if event_type.startswith("delivery.") and aggregate_id:
            await self.broadcast_to_channel(f"delivery:{aggregate_id}", event_data)

        # 3. Driver channel (if driver-related)
        driver_id = data.get("driver_id", "") or (aggregate_id if event_type.startswith("driver.") else "")
        if driver_id:
            await self.broadcast_to_channel(f"driver:{driver_id}", event_data)

        # 4. Operations channel (for admin map / alerts)
        if event_type.startswith("driver.location"):
            if tenant_id:
                await self.broadcast_to_channel(f"operations:{tenant_id}", event_data)

    def get_stats(self) -> dict:
        """Get connection statistics."""
        return {
            "total_connections": len(self._connections),
            "channels": {ch: len(conns) for ch, conns in self._channels.items()},
            "total_connected_lifetime": self._total_connected,
            "total_events_sent": self._total_events_sent,
        }


# ── Singleton ────────────────────────────────────────────

_manager: Optional[ConnectionManager] = None


def get_ws_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


# ── Event Bus → WebSocket bridge ────────────────────────


def _event_to_ws(event: DomainEvent):
    """Synchronous handler called by Event Bus. Schedules async broadcast."""
    manager = get_ws_manager()
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(manager.broadcast_event(event))
        else:
            loop.run_until_complete(manager.broadcast_event(event))
    except RuntimeError:
        # No event loop — skip (will be caught on next connect)
        pass


def setup_realtime_bridge():
    """Subscribe the WebSocket manager to the Event Bus."""
    bus = get_event_bus()

    # Subscribe to delivery, driver and order events
    for event_type in EventType:
        prefix = event_type.value.split(".", 1)[0]
        if prefix in ("delivery", "driver", "order"):
            bus.subscribe(event_type, _event_to_ws)

    logger.info("Realtime bridge: Event Bus → WebSocket connected")


def start_cross_worker_listener(url: Optional[str] = None):
    """Start the Redis pub/sub listener that relays other workers' events.

    Called from the FastAPI lifespan when settings.realtime_backend == "redis"
    (multi-worker deployments). Returns the task and the pubsub object so the
    caller can cancel the task on shutdown. In single-worker mode this is
    never invoked — the in-process bus is sufficient.
    """
    from app.infrastructure.realtime.pubsub import RedisPubSub

    manager = get_ws_manager()
    pubsub = RedisPubSub(url=url)
    manager.enable_pubsub(pubsub)
    task = asyncio.create_task(pubsub.listen_forever(manager.broadcast_event_dict))
    logger.info(
        "Cross-worker realtime: Redis pub/sub listener started (%s)",
        pubsub.worker_id,
    )
    return task, pubsub


# ── WebSocket Endpoints ─────────────────────────────────


def _verify_ws_token(token: str) -> Optional[dict]:
    """Verify token and return metadata. Returns None if invalid.

    Uses database for auth (single source of truth).
    Falls back to shared_store only for driver sessions (already persisted).
    """
    if not token:
        return None

    # Try admin/operator auth via AuthService (DB-backed)
    try:
        from app.presentation.dependencies import get_auth_service

        auth = get_auth_service()
        ctx = auth.validate_token(token)
        if ctx and ctx.is_authenticated:
            return {
                "user_id": ctx.user_id,
                "tenant_id": ctx.tenant_id,
                "role": ctx.role.value if hasattr(ctx.role, "value") else str(ctx.role),
                "driver_id": "",
            }
    except Exception:
        # Token inválido/expirado cai no fluxo de driver auth abaixo.
        logger.debug("ws.token_auth_failed", exc_info=True)

    # Try driver auth via DB session
    try:
        from sqlalchemy.orm import Session as DBSession
        from app.infrastructure.database.init_db import engine
        from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDriverSessionRepository

        db = DBSession(bind=engine)
        try:
            session_repo = SQLAlchemyDriverSessionRepository(db)
            record = session_repo.get_session(token)
            if record:
                return {
                    "user_id": record.driver_id,
                    "tenant_id": record.tenant_id,
                    "role": "DRIVER",
                    "driver_id": record.driver_id,
                }
        finally:
            db.close()
    except Exception:
        logger.debug("ws.driver_session_auth_failed", exc_info=True)

    return None


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    channel: str = Query(default=""),
):
    """
    WebSocket endpoint for realtime events.

    Channels:
        tenant:{id}     → admin dashboard events
        driver:{id}     → driver app events
        delivery:{id}   → specific delivery events
        operations:{id} → admin operations (map, alerts)
    """
    # Authenticate
    meta = _verify_ws_token(token)
    if not meta:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Derive channel from role if not specified
    if not channel:
        if meta["role"] == "DRIVER" and meta.get("driver_id"):
            channel = f"driver:{meta['driver_id']}"
        else:
            channel = f"tenant:{meta['tenant_id']}"

    # Security: ensure channel matches tenant
    if meta["tenant_id"] and meta["tenant_id"] not in channel:
        await websocket.close(code=4003, reason="Forbidden: tenant mismatch")
        return

    manager = get_ws_manager()
    await manager.connect(websocket, channel, meta)

    # Send welcome
    await websocket.send_text(
        json.dumps(
            {
                "type": "connected",
                "channel": channel,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
    )

    try:
        while True:
            # Keep connection alive, receive pings
            data = await websocket.receive_text()

            # Handle ping/pong
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif data == "stats":
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "stats",
                            **manager.get_stats(),
                        }
                    )
                )
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.debug("ws.unexpected_disconnect — cleaning up connection", exc_info=True)
        manager.disconnect(websocket)


@router.get("/realtime/stats")
async def realtime_stats():
    """Get WebSocket connection statistics."""
    manager = get_ws_manager()
    return manager.get_stats()
