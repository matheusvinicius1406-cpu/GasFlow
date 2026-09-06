"""
Event Bus — Domain Event System

Lightweight event bus for delivery lifecycle events.
Used for: dispatch notifications, communication triggers, realtime updates.

Events:
  DeliveryAssigned, DeliveryAccepted, DeliveryStarted,
  DeliveryArrived, DeliveryCompleted, DeliveryFailed,
  DriverAvailable, DriverLocationUpdated, DispatchReplanned
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from enum import Enum
import uuid
import threading


class EventType(str, Enum):
    # Delivery events
    DELIVERY_CREATED = "delivery.created"
    DELIVERY_ASSIGNED = "delivery.assigned"
    DELIVERY_ACCEPTED = "delivery.accepted"
    DELIVERY_STARTED = "delivery.started"
    DELIVERY_ARRIVED = "delivery.arrived"
    DELIVERY_COMPLETED = "delivery.completed"
    DELIVERY_FAILED = "delivery.failed"
    DELIVERY_CANCELLED = "delivery.cancelled"

    # Driver events
    DRIVER_AVAILABLE = "driver.available"
    DRIVER_UNAVAILABLE = "driver.unavailable"
    DRIVER_LOCATION_UPDATED = "driver.location_updated"
    DRIVER_PAUSED = "driver.paused"

    # Order events
    ORDER_CREATED = "order.created"
    ORDER_UPDATED = "order.updated"

    # Dispatch events
    DISPATCH_RECOMMENDED = "dispatch.recommended"
    DISPATCH_ASSIGNED = "dispatch.assigned"
    DISPATCH_REPLANNED = "dispatch.replanned"

    # Communication events
    COMMUNICATION_PROXIMITY = "communication.proximity"
    COMMUNICATION_ARRIVAL = "communication.arrival"
    COMMUNICATION_ABSENT = "communication.absent"
    COMMUNICATION_DELAY = "communication.delay"
    COMMUNICATION_POST_DELIVERY = "communication.post_delivery"

    # Payment events
    PAYMENT_CONFIRMED = "payment.confirmed"
    PAYMENT_PENDING = "payment.pending"


@dataclass
class DomainEvent:
    """Immutable domain event."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: EventType = EventType.DELIVERY_CREATED
    tenant_id: str = ""
    aggregate_id: str = ""  # delivery_id, driver_id, etc.
    actor_id: str = ""  # who triggered
    actor_type: str = "SYSTEM"  # OPERATOR, DRIVER, SYSTEM
    timestamp: datetime = field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "tenant_id": self.tenant_id,
            "aggregate_id": self.aggregate_id,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "metadata": self.metadata,
        }


# Event handler type
EventHandler = Callable[[DomainEvent], None]


class EventBus:
    """
    In-memory event bus with thread-safe publish/subscribe.

    Usage:
        bus = EventBus()

        def on_delivery_completed(event: DomainEvent):
            print(f"Delivery {event.aggregate_id} completed!")

        bus.subscribe(EventType.DELIVERY_COMPLETED, on_delivery_completed)
        bus.publish(DomainEvent(type=EventType.DELIVERY_COMPLETED, aggregate_id="d1"))
    """

    def __init__(self):
        self._handlers: Dict[EventType, List[EventHandler]] = {}
        self._lock = threading.Lock()
        self._history: List[DomainEvent] = []
        self._max_history = 1000

    def subscribe(self, event_type: EventType, handler: EventHandler):
        """Subscribe to an event type."""
        with self._lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler):
        """Unsubscribe from an event type."""
        with self._lock:
            if event_type in self._handlers:
                self._handlers[event_type] = [h for h in self._handlers[event_type] if h != handler]

    def publish(self, event: DomainEvent):
        """Publish an event to all subscribers."""
        # Store in history
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]

        # Notify handlers (copy list to avoid modification during iteration)
        handlers = list(self._handlers.get(event.type, []))
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                # Don't let handler errors break the bus
                pass

    def get_history(self, event_type: Optional[EventType] = None, limit: int = 50) -> List[DomainEvent]:
        """Get recent events, optionally filtered by type."""
        with self._lock:
            events = self._history
            if event_type:
                events = [e for e in events if e.type == event_type]
            return events[-limit:]

    def clear_history(self):
        """Clear event history."""
        with self._lock:
            self._history.clear()


# ── Singleton instance ───────────────────────────────────

_global_bus = EventBus()


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    return _global_bus


# ── Convenience functions ────────────────────────────────


def publish_delivery_event(
    event_type: EventType,
    delivery_id: str,
    tenant_id: str,
    driver_id: str = "",
    data: Optional[Dict] = None,
):
    """Publish a delivery lifecycle event."""
    event = DomainEvent(
        type=event_type,
        tenant_id=tenant_id,
        aggregate_id=delivery_id,
        actor_id=driver_id,
        actor_type="DRIVER" if driver_id else "SYSTEM",
        data=data or {},
    )
    _global_bus.publish(event)
    return event


def publish_driver_event(
    event_type: EventType,
    driver_id: str,
    tenant_id: str,
    data: Optional[Dict] = None,
):
    """Publish a driver lifecycle event."""
    event = DomainEvent(
        type=event_type,
        tenant_id=tenant_id,
        aggregate_id=driver_id,
        actor_id=driver_id,
        actor_type="DRIVER",
        data=data or {},
    )
    _global_bus.publish(event)
    return event


def publish_order_event(
    event_type: EventType,
    order_codigo: str,
    tenant_id: str,
    data: Optional[Dict] = None,
):
    """Publish an order lifecycle event (created, updated/status changed)."""
    event = DomainEvent(
        type=event_type,
        tenant_id=tenant_id,
        aggregate_id=order_codigo,
        actor_id="",
        actor_type="OPERATOR",
        data=data or {},
    )
    _global_bus.publish(event)
    return event
