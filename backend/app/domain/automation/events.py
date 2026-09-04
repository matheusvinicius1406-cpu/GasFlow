"""
Domain Events — FASE 12

Event contract, event types, event bus abstraction, and outbox pattern.
Events are immutable facts — never mutated after creation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from enum import Enum
import uuid
import threading


# ── Event Types ─────────────────────────────────────────

class EventType(str, Enum):
    # CRM
    CUSTOMER_CREATED = "CUSTOMER_CREATED"
    CUSTOMER_UPDATED = "CUSTOMER_UPDATED"
    CUSTOMER_INACTIVE = "CUSTOMER_INACTIVE"
    # Orders
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    ORDER_PREPARING = "ORDER_PREPARING"
    ORDER_DELIVERING = "ORDER_DELIVERING"
    ORDER_DELIVERED = "ORDER_DELIVERED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    # Inventory
    INVENTORY_LOW = "INVENTORY_LOW"
    INVENTORY_OUT = "INVENTORY_OUT"
    INVENTORY_ADJUSTED = "INVENTORY_ADJUSTED"
    # Financial
    PAYMENT_CREATED = "PAYMENT_CREATED"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    RECEIVABLE_OVERDUE = "RECEIVABLE_OVERDUE"
    # WhatsApp
    WHATSAPP_MESSAGE_RECEIVED = "WHATSAPP_MESSAGE_RECEIVED"
    WHATSAPP_MESSAGE_SENT = "WHATSAPP_MESSAGE_SENT"
    CONVERSATION_HUMAN_HANDOFF = "CONVERSATION_HUMAN_HANDOFF"
    # Automation
    WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED"
    WORKFLOW_FAILED = "WORKFLOW_FAILED"
    AGENT_COMPLETED = "AGENT_COMPLETED"
    AGENT_FAILED = "AGENT_FAILED"
    # Generic
    CUSTOM = "CUSTOM"


# ── Event Contract ──────────────────────────────────────

@dataclass
class DomainEvent:
    """Immutable domain event."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = EventType.CUSTOM
    occurred_at: datetime = field(default_factory=datetime.utcnow)
    aggregate_type: str = ""
    aggregate_id: str = ""
    source: str = ""
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    version: int = 1

    @property
    def idempotency_key(self) -> str:
        """Key for deduplication."""
        return f"{self.event_type.value}:{self.aggregate_type}:{self.aggregate_id}:{self.event_id}"


# ── Event Bus ───────────────────────────────────────────

class EventBus:
    """In-process event bus with handler registration."""

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
        self._event_log: List[DomainEvent] = []

    def subscribe(self, event_type: EventType, handler: Callable):
        """Subscribe a handler to an event type."""
        with self._lock:
            key = event_type.value
            if key not in self._handlers:
                self._handlers[key] = []
            self._handlers[key].append(handler)

    def publish(self, event: DomainEvent) -> bool:
        """Publish an event to all subscribed handlers."""
        with self._lock:
            self._event_log.append(event)
            handlers = self._handlers.get(event.event_type.value, [])

        if not handlers:
            return True

        success = True
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                success = False
        return success

    def get_log(self, limit: int = 50) -> List[DomainEvent]:
        """Get recent events."""
        return self._event_log[-limit:]

    def clear_log(self):
        with self._lock:
            self._event_log.clear()


# ── Outbox ──────────────────────────────────────────────

class OutboxEntry:
    """Outbox entry for transactional event publishing."""

    def __init__(self, event: DomainEvent, status: str = "PENDING"):
        self.id: Optional[int] = None
        self.event = event
        self.status = status  # PENDING, DISPATCHED, FAILED
        self.attempts = 0
        self.max_retries = 3
        self.created_at = datetime.utcnow()
        self.dispatched_at: Optional[datetime] = None
        self.error: Optional[str] = None

    @property
    def should_retry(self) -> bool:
        return self.status == "FAILED" and self.attempts < self.max_retries


class OutboxStore:
    """In-memory outbox store for events that need to survive processing."""

    def __init__(self):
        self._entries: List[OutboxEntry] = []
        self._lock = threading.Lock()
        self._dispatched: List[OutboxEntry] = []

    def add(self, event: DomainEvent) -> OutboxEntry:
        entry = OutboxEntry(event)
        with self._lock:
            self._entries.append(entry)
        return entry

    def mark_dispatched(self, entry: OutboxEntry):
        with self._lock:
            entry.status = "DISPATCHED"
            entry.dispatched_at = datetime.utcnow()
            self._dispatched.append(entry)

    def mark_failed(self, entry: OutboxEntry, error: str):
        with self._lock:
            entry.status = "FAILED"
            entry.attempts += 1
            entry.error = error

    def get_pending(self) -> List[OutboxEntry]:
        with self._lock:
            return [e for e in self._entries if e.status == "PENDING"]

    def get_retryable(self) -> List[OutboxEntry]:
        with self._lock:
            return [e for e in self._entries if e.should_retry]

    def get_dispatched(self) -> List[OutboxEntry]:
        with self._lock:
            return list(self._dispatched)
