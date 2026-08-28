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
from typing import Dict, Set, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from datetime import datetime

from app.domain.events.event_bus import get_event_bus, EventType, DomainEvent

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
                dead.append(ws)
        
        # Clean up dead connections
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_event(self, event: DomainEvent):
        """Route an Event Bus event to appropriate WebSocket channels."""
        event_data = {
            "type": "event",
            "event": event.to_dict(),
        }
        
        # 1. Tenant channel (admin dashboard)
        if event.tenant_id:
            await self.broadcast_to_channel(f"tenant:{event.tenant_id}", event_data)
        
        # 2. Delivery channel (if delivery-related)
        delivery_id = event.aggregate_id if event.type.value.startswith("delivery.") else ""
        if delivery_id:
            await self.broadcast_to_channel(
                f"delivery:{delivery_id}", event_data
            )
        
        # 3. Driver channel (if driver-related)
        driver_id = event.data.get("driver_id", "") or (
            event.aggregate_id if event.type.value.startswith("driver.") else ""
        )
        if driver_id:
            await self.broadcast_to_channel(
                f"driver:{driver_id}", event_data
            )
        
        # 4. Operations channel (for admin map / alerts)
        if event.type.value.startswith("driver.location"):
            if event.tenant_id:
                await self.broadcast_to_channel(
                    f"operations:{event.tenant_id}", event_data
                )

    def get_stats(self) -> dict:
        """Get connection statistics."""
        return {
            "total_connections": len(self._connections),
            "channels": {
                ch: len(conns) for ch, conns in self._channels.items()
            },
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
    
    # Subscribe to all delivery events
    for event_type in EventType:
        if event_type.value.startswith("delivery.") or event_type.value.startswith("driver."):
            bus.subscribe(event_type, _event_to_ws)
    
    logger.info("Realtime bridge: Event Bus → WebSocket connected")


# ── WebSocket Endpoints ─────────────────────────────────

def _verify_ws_token(token: str) -> Optional[dict]:
    """Verify token and return metadata. Returns None if invalid."""
    if not token:
        return None
    
    from app.infrastructure.stores.shared_store import get_shared_store
    store = get_shared_store()
    
    session = store.get("sessions", {}).get(token)
    if not session:
        return None
    
    return {
        "user_id": session.get("user_id", ""),
        "tenant_id": session.get("tenant_id", ""),
        "role": session.get("role", ""),
        "driver_id": session.get("driver_id", ""),
    }


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
    await websocket.send_text(json.dumps({
        "type": "connected",
        "channel": channel,
        "timestamp": datetime.utcnow().isoformat(),
    }))
    
    try:
        while True:
            # Keep connection alive, receive pings
            data = await websocket.receive_text()
            
            # Handle ping/pong
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif data == "stats":
                await websocket.send_text(json.dumps({
                    "type": "stats",
                    **manager.get_stats(),
                }))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


@router.get("/realtime/stats")
async def realtime_stats():
    """Get WebSocket connection statistics."""
    manager = get_ws_manager()
    return manager.get_stats()
