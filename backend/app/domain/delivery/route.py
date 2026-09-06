"""
Route + RouteStop Domain Entities — FASE 14

Route: sequence of delivery stops for a driver.
RouteStop: individual stop within a route.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
import uuid


class RouteStatus(str, Enum):
    PLANNED = "PLANNED"
    DISPATCHED = "DISPATCHED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class StopStatus(str, Enum):
    PENDING = "PENDING"
    ARRIVED = "ARRIVED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


# Valid route transitions
ROUTE_TRANSITIONS = {
    RouteStatus.PLANNED: {RouteStatus.DISPATCHED, RouteStatus.CANCELLED},
    RouteStatus.DISPATCHED: {RouteStatus.IN_PROGRESS, RouteStatus.CANCELLED},
    RouteStatus.IN_PROGRESS: {RouteStatus.COMPLETED, RouteStatus.CANCELLED},
    RouteStatus.COMPLETED: set(),
    RouteStatus.CANCELLED: set(),
}

STOP_TRANSITIONS = {
    StopStatus.PENDING: {StopStatus.ARRIVED, StopStatus.FAILED, StopStatus.SKIPPED},
    StopStatus.ARRIVED: {StopStatus.COMPLETED, StopStatus.FAILED},
    StopStatus.COMPLETED: set(),
    StopStatus.FAILED: set(),
    StopStatus.SKIPPED: set(),
}


@dataclass
class RouteStop:
    """A single stop in a delivery route."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    route_id: str = ""
    delivery_id: str = ""
    sequence: int = 0
    status: StopStatus = StopStatus.PENDING
    eta_minutes: Optional[int] = None
    arrived_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    notes: str = ""
    # Customer info snapshot
    customer_name: str = ""
    customer_phone: str = ""
    address_snapshot: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    def can_transition(self, new_status: StopStatus) -> bool:
        return new_status in STOP_TRANSITIONS.get(self.status, set())

    def arrive(self) -> bool:
        if not self.can_transition(StopStatus.ARRIVED):
            return False
        self.status = StopStatus.ARRIVED
        self.arrived_at = datetime.utcnow()
        return True

    def complete(self) -> bool:
        if not self.can_transition(StopStatus.COMPLETED):
            return False
        self.status = StopStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        return True

    def fail(self, reason: str = "") -> bool:
        if not self.can_transition(StopStatus.FAILED):
            return False
        self.status = StopStatus.FAILED
        self.failure_reason = reason
        return True

    def skip(self) -> bool:
        if not self.can_transition(StopStatus.SKIPPED):
            return False
        self.status = StopStatus.SKIPPED
        return True

    @property
    def is_terminal(self) -> bool:
        return self.status in {StopStatus.COMPLETED, StopStatus.FAILED, StopStatus.SKIPPED}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "route_id": self.route_id,
            "delivery_id": self.delivery_id,
            "sequence": self.sequence,
            "status": self.status.value,
            "eta_minutes": self.eta_minutes,
            "arrived_at": self.arrived_at.isoformat() if self.arrived_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "failure_reason": self.failure_reason,
            "notes": self.notes,
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "address_snapshot": self.address_snapshot,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Route:
    """A planned route with ordered stops."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    driver_id: str = ""
    vehicle_id: Optional[str] = None
    date: Optional[datetime] = None
    status: RouteStatus = RouteStatus.PLANNED
    stops: List[RouteStop] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    dispatched_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def can_transition(self, new_status: RouteStatus) -> bool:
        return new_status in ROUTE_TRANSITIONS.get(self.status, set())

    def transition(self, new_status: RouteStatus) -> bool:
        if not self.can_transition(new_status):
            return False
        self.status = new_status
        self.updated_at = datetime.utcnow()
        if new_status == RouteStatus.DISPATCHED:
            self.dispatched_at = datetime.utcnow()
        elif new_status == RouteStatus.COMPLETED:
            self.completed_at = datetime.utcnow()
        return True

    def add_stop(
        self,
        delivery_id: str,
        sequence: int,
        customer_name: str = "",
        customer_phone: str = "",
        address_snapshot: str = "",
    ) -> RouteStop:
        """Add a stop to the route. Validates sequence uniqueness."""
        # Check sequence uniqueness
        existing_sequences = {s.sequence for s in self.stops}
        if sequence in existing_sequences:
            raise ValueError(f"Sequence {sequence} already exists in route")
        stop = RouteStop(
            route_id=self.id,
            delivery_id=delivery_id,
            sequence=sequence,
            customer_name=customer_name,
            customer_phone=customer_phone,
            address_snapshot=address_snapshot,
        )
        self.stops.append(stop)
        self.stops.sort(key=lambda s: s.sequence)
        self.updated_at = datetime.utcnow()
        return stop

    def remove_stop(self, stop_id: str) -> bool:
        for i, stop in enumerate(self.stops):
            if stop.id == stop_id and stop.status == StopStatus.PENDING:
                self.stops.pop(i)
                self.updated_at = datetime.utcnow()
                return True
        return False

    def get_pending_stops(self) -> List[RouteStop]:
        return [s for s in self.stops if s.status == StopStatus.PENDING]

    def get_next_stop(self) -> Optional[RouteStop]:
        pending = self.get_pending_stops()
        return pending[0] if pending else None

    @property
    def progress_pct(self) -> float:
        if not self.stops:
            return 0.0
        completed = sum(1 for s in self.stops if s.is_terminal)
        return (completed / len(self.stops)) * 100

    def dispatch(self) -> bool:
        return self.transition(RouteStatus.DISPATCHED)

    def start(self) -> bool:
        return self.transition(RouteStatus.IN_PROGRESS)

    def complete_route(self) -> bool:
        return self.transition(RouteStatus.COMPLETED)

    def cancel(self) -> bool:
        return self.transition(RouteStatus.CANCELLED)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "driver_id": self.driver_id,
            "vehicle_id": self.vehicle_id,
            "date": self.date.isoformat() if self.date else None,
            "status": self.status.value,
            "stops": [s.to_dict() for s in self.stops],
            "progress_pct": self.progress_pct,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "dispatched_at": self.dispatched_at.isoformat() if self.dispatched_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
