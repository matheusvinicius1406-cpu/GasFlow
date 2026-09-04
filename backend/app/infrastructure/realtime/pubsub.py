"""
Redis Pub/Sub — cross-worker event propagation for the WebSocket manager.

Why: production runs uvicorn with BACKEND_WORKERS > 1. Each worker process
has its own in-process Event Bus + ConnectionManager, so an event raised in
worker A (e.g. a driver REST call landing on A) would never reach WebSocket
clients connected to worker B without a shared transport.

Flow with REALTIME_BACKEND=redis:
    Domain Event → Event Bus → _event_to_ws (worker A)
        → broadcast locally to A's clients
        → PUBLISH "gasflow:events" {origin: A, event: {...}}
    Worker B (and A) receive the message; the listener skips messages whose
    origin is itself (A already broadcast locally) and routes foreign events
    to B's local clients.

The subscriber is async (redis.asyncio) because it runs as a background task
started in the FastAPI lifespan. Publishing uses the same async client.

Reuses the configured Redis URL (settings.realtime_redis_url, same default
as the rate limiter) so no new infra is required in the compose stacks.
"""

import json
import logging
import os
import uuid
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger("gasflow.realtime.pubsub")

# Redis channel shared by all workers.
EVENTS_CHANNEL = "gasflow:events"

# Unique id per worker process — used to skip our own published messages
# (the origin worker already broadcast locally, avoiding duplicates).
_worker_id = os.getenv("REALTIME_WORKER_ID", f"proc-{uuid.uuid4().hex[:12]}")


class RedisPubSub:
    """Publish DomainEvents to Redis and consume other workers' events."""

    def __init__(
        self,
        url: Optional[str] = None,
        channel: str = EVENTS_CHANNEL,
        worker_id: Optional[str] = None,
    ):
        self._url = url or settings.realtime_redis_url
        self._channel = channel
        self.worker_id = worker_id or _worker_id
        self._client = None  # lazy async redis client

    def _connect(self):
        """Lazy async Redis client creation (import redis only when used)."""
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(
                self._url,
                socket_connect_timeout=2.0,
                socket_timeout=2.0,
            )
        return self._client

    async def publish_event(self, event_data: Dict[str, Any]) -> None:
        """Publish a domain event dict so other workers can broadcast it."""
        message = json.dumps(
            {"origin": self.worker_id, "event": event_data},
            default=str,
        )
        try:
            await self._connect().publish(self._channel, message)
        except Exception:
            # Never let cross-worker propagation break the request/event.
            logger.warning("Redis publish failed — event not propagated", exc_info=True)

    @staticmethod
    def decode_message(payload: str) -> Optional[Dict[str, Any]]:
        """Decode a Redis message body. Returns None for malformed payloads."""
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            return None
        if not isinstance(data, dict) or "event" not in data:
            return None
        return data

    def is_own_message(self, message: Dict[str, Any]) -> bool:
        """True when the message was published by this worker (already local)."""
        return message.get("origin") == self.worker_id

    async def listen_forever(self, on_event) -> None:
        """Consume the shared channel and hand foreign events to ``on_event``.

        Runs forever — the caller is responsible for cancelling the task on
        shutdown. ``on_event`` is an async callable receiving the event dict.
        """
        client = self._connect()
        pubsub = client.pubsub()
        await pubsub.subscribe(self._channel)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = self.decode_message(message.get("data"))
                if not data or self.is_own_message(data):
                    continue
                event = data.get("event")
                if isinstance(event, dict):
                    try:
                        await on_event(event)
                    except Exception:
                        logger.warning(
                            "Error handling cross-worker event", exc_info=True
                        )
        finally:
            await pubsub.unsubscribe(self._channel)
            await pubsub.close()
