"""
Delivery Domain Entity — FASE 14

Physical operation representing an Order's transport.
State machine enforced. No direct DB access.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
import uuid


class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    DISPATCHED = "DISPATCHED"
    EN_ROUTE = "EN_ROUTE"
    ARRIVED = "ARRIVED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"


class DeliveryFailureReason(str, Enum):
    CUSTOMER_ABSENT = "CUSTOMER_ABSENT"
    ADDRESS_INVALID = "ADDRESS_INVALID"
    REFUSED = "REFUSED"
    DAMAGED = "DAMAGED"
    VEHICLE_FAILURE = "VEHICLE_FAILURE"
    WEATHER = "WEATHER"
    OTHER = "OTHER"


class ProofType(str, Enum):
    PHOTO = "PHOTO"
    SIGNATURE = "SIGNATURE"
    OTP = "OTP"
    MANUAL_CONFIRMATION = "MANUAL_CONFIRMATION"


# Valid state transitions
DELIVERY_TRANSITIONS = {
    DeliveryStatus.PENDING: {DeliveryStatus.ASSIGNED, DeliveryStatus.CANCELLED},
    DeliveryStatus.ASSIGNED: {DeliveryStatus.DISPATCHED, DeliveryStatus.CANCELLED},
    DeliveryStatus.DISPATCHED: {DeliveryStatus.EN_ROUTE, DeliveryStatus.CANCELLED},
    DeliveryStatus.EN_ROUTE: {DeliveryStatus.ARRIVED, DeliveryStatus.FAILED, DeliveryStatus.CANCELLED},
    DeliveryStatus.ARRIVED: {DeliveryStatus.DELIVERED, DeliveryStatus.FAILED, DeliveryStatus.CANCELLED},
    DeliveryStatus.DELIVERED: set(),  # Terminal
    DeliveryStatus.FAILED: {DeliveryStatus.RESCHEDULED, DeliveryStatus.CANCELLED},
    DeliveryStatus.CANCELLED: set(),  # Terminal
    DeliveryStatus.RESCHEDULED: {DeliveryStatus.PENDING},  # Back to pending
}


@dataclass
class DeliveryProof:
    """Proof of delivery."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    delivery_id: str = ""
    proof_type: ProofType = ProofType.MANUAL_CONFIRMATION
    file_path: Optional[str] = None  # For photo/signature
    otp_code: Optional[str] = None
    confirmed_by: str = ""
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DeliveryTimeline:
    """Immutable timeline event."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    delivery_id: str = ""
    status: DeliveryStatus = DeliveryStatus.PENDING
    actor_id: str = ""
    actor_type: str = "OPERATOR"  # OPERATOR, DRIVER, SYSTEM
    timestamp: datetime = field(default_factory=datetime.utcnow)
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AddressSnapshot:
    """Frozen copy of delivery address at order time."""

    street: str = ""
    number: str = ""
    complement: str = ""
    neighborhood: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    reference: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None

    def full_address(self) -> str:
        parts = [self.street]
        if self.number:
            parts[-1] += f", {self.number}"
        if self.complement:
            parts[-1] += f" {self.complement}"
        if self.neighborhood:
            parts.append(self.neighborhood)
        if self.city:
            parts.append(self.city)
        if self.state:
            parts[-1] += f" - {self.state}"
        if self.zip_code:
            parts.append(self.zip_code)
        return ", ".join(parts)


@dataclass
class Delivery:
    """Physical operation of delivering an order."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str = ""
    tenant_id: str = ""
    status: DeliveryStatus = DeliveryStatus.PENDING
    customer_codigo: str = ""
    customer_name: str = ""
    address: AddressSnapshot = field(default_factory=AddressSnapshot)
    driver_id: Optional[str] = None
    vehicle_id: Optional[str] = None
    route_id: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    arrived_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    failed_reason: Optional[DeliveryFailureReason] = None
    failure_notes: str = ""
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    proof: Optional[DeliveryProof] = None
    timeline: List[DeliveryTimeline] = field(default_factory=list)

    def can_transition(self, new_status: DeliveryStatus) -> bool:
        return new_status in DELIVERY_TRANSITIONS.get(self.status, set())

    def transition(
        self,
        new_status: DeliveryStatus,
        actor_id: str = "",
        actor_type: str = "OPERATOR",
        notes: str = "",
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Attempt state transition. Returns True if successful."""
        if not self.can_transition(new_status):
            return False
        old_status = self.status
        self.status = new_status
        self.updated_at = datetime.utcnow()

        # Set timestamps
        now = datetime.utcnow()
        if new_status == DeliveryStatus.ASSIGNED:
            pass
        elif new_status == DeliveryStatus.DISPATCHED:
            self.started_at = now
        elif new_status == DeliveryStatus.ARRIVED:
            self.arrived_at = now
        elif new_status == DeliveryStatus.DELIVERED:
            self.delivered_at = now
        elif new_status == DeliveryStatus.FAILED:
            self.failed_at = now
        elif new_status == DeliveryStatus.RESCHEDULED:
            # Keep history, reset for new attempt
            self.driver_id = None
            self.vehicle_id = None
            self.route_id = None
            self.started_at = None
            self.arrived_at = None

        # Add timeline event
        self.timeline.append(
            DeliveryTimeline(
                delivery_id=self.id,
                status=new_status,
                actor_id=actor_id,
                actor_type=actor_type,
                notes=notes,
                metadata=metadata or {},
            )
        )
        return True

    def assign(self, driver_id: str, vehicle_id: Optional[str] = None, route_id: Optional[str] = None) -> bool:
        """Assign driver and optionally vehicle/route."""
        if not self.can_transition(DeliveryStatus.ASSIGNED):
            return False
        self.driver_id = driver_id
        if vehicle_id:
            self.vehicle_id = vehicle_id
        if route_id:
            self.route_id = route_id
        return self.transition(DeliveryStatus.ASSIGNED, actor_type="OPERATOR")

    def dispatch(self) -> bool:
        return self.transition(DeliveryStatus.DISPATCHED, actor_type="OPERATOR")

    def start_route(self) -> bool:
        return self.transition(DeliveryStatus.EN_ROUTE, actor_type="DRIVER")

    def arrive(self) -> bool:
        return self.transition(DeliveryStatus.ARRIVED, actor_type="DRIVER")

    def complete(self, proof: Optional[DeliveryProof] = None) -> bool:
        if proof:
            self.proof = proof
        return self.transition(DeliveryStatus.DELIVERED, actor_type="DRIVER")

    def fail(self, reason: DeliveryFailureReason, notes: str = "") -> bool:
        self.failed_reason = reason
        self.failure_notes = notes
        return self.transition(DeliveryStatus.FAILED, actor_type="DRIVER", notes=notes)

    def cancel(self, actor_type: str = "OPERATOR") -> bool:
        return self.transition(DeliveryStatus.CANCELLED, actor_type=actor_type)

    def reschedule(self) -> bool:
        return self.transition(DeliveryStatus.RESCHEDULED, actor_type="OPERATOR")

    @property
    def eta_minutes(self) -> Optional[int]:
        """Estimate remaining minutes. Requires route/ETA data."""
        if self.scheduled_at and self.started_at:
            delta = self.scheduled_at - datetime.utcnow()
            return max(0, int(delta.total_seconds() / 60))
        return None

    @property
    def is_active(self) -> bool:
        return self.status not in {DeliveryStatus.DELIVERED, DeliveryStatus.CANCELLED}

    @property
    def customer_can_track(self) -> bool:
        return self.status in {
            DeliveryStatus.ASSIGNED,
            DeliveryStatus.DISPATCHED,
            DeliveryStatus.EN_ROUTE,
            DeliveryStatus.ARRIVED,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "tenant_id": self.tenant_id,
            "status": self.status.value,
            "customer_codigo": self.customer_codigo,
            "customer_name": self.customer_name,
            "driver_id": self.driver_id,
            "vehicle_id": self.vehicle_id,
            "route_id": self.route_id,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "arrived_at": self.arrived_at.isoformat() if self.arrived_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None,
            "failed_reason": self.failed_reason.value if self.failed_reason else None,
            "failure_notes": self.failure_notes,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "address": {
                "street": self.address.street,
                "number": self.address.number,
                "complement": self.address.complement,
                "neighborhood": self.address.neighborhood,
                "city": self.address.city,
                "state": self.address.state,
                "zip_code": self.address.zip_code,
                "reference": self.address.reference,
            },
            "timeline": [
                {
                    "status": t.status.value,
                    "timestamp": t.timestamp.isoformat(),
                    "actor_type": t.actor_type,
                    "notes": t.notes,
                }
                for t in self.timeline
            ],
            "eta_minutes": self.eta_minutes,
        }
