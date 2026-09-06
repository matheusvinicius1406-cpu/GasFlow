"""
Delivery Persistence Model — SQLAlchemy model for delivery lifecycle.

This model backs the Delivery domain entity with real database persistence.
Replaces the in-memory store used in driver_api.py.

Includes:
- Delivery lifecycle (PENDING → ASSIGNED → EN_ROUTE → ARRIVED → DELIVERED/FAILED)
- Driver assignment
- GPS locations
- Outbox entries for event delivery
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, JSON, Index, UniqueConstraint
from datetime import datetime
from app.infrastructure.database.base import Base


class DeliveryRecord(Base):
    """Persistent delivery record — single source of truth."""

    __tablename__ = "delivery_records"

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_delivery_idempotency"),
        Index("ix_delivery_tenant_status", "tenant_id", "status"),
        Index("ix_delivery_tenant_driver", "tenant_id", "driver_id"),
        Index("ix_delivery_order", "order_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    delivery_id = Column(String(36), unique=True, nullable=False, index=True)
    tenant_id = Column(String, default="default", nullable=False, index=True)
    order_id = Column(String(36), nullable=False, index=True)

    # State machine
    status = Column(String(20), default="PENDING", nullable=False)
    version = Column(Integer, default=1, nullable=False)

    # Customer
    customer_codigo = Column(String(10), default="")
    customer_name = Column(String(200), default="")

    # Address snapshot
    address_street = Column(String(200), default="")
    address_number = Column(String(20), default="")
    address_complement = Column(String(100), default="")
    address_neighborhood = Column(String(100), default="")
    address_city = Column(String(100), default="")
    address_state = Column(String(2), default="")
    address_zip_code = Column(String(10), default="")
    address_reference = Column(String(200), default="")
    address_lat = Column(Float, nullable=True)
    address_lng = Column(Float, nullable=True)

    # Assignment
    driver_id = Column(String(36), nullable=True, index=True)
    vehicle_id = Column(String(36), nullable=True)
    route_id = Column(String(36), nullable=True)

    # Timestamps
    scheduled_at = Column(DateTime, nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    arrived_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Failure
    failed_reason = Column(String(50), nullable=True)
    failure_notes = Column(Text, default="")

    # Proof
    proof_type = Column(String(30), nullable=True)
    proof_data = Column(JSON, nullable=True)

    # Notes
    notes = Column(Text, default="")
    driver_notes = Column(Text, default="")

    # Idempotency
    idempotency_key = Column(String(100), nullable=True)

    # Timeline as JSON array
    timeline = Column(JSON, default=list)

    def to_dict(self) -> dict:
        return {
            "id": self.delivery_id,
            "order_id": self.order_id,
            "tenant_id": self.tenant_id,
            "status": self.status,
            "version": self.version,
            "customer_codigo": self.customer_codigo,
            "customer_name": self.customer_name,
            "address": {
                "street": self.address_street,
                "number": self.address_number,
                "complement": self.address_complement,
                "neighborhood": self.address_neighborhood,
                "city": self.address_city,
                "state": self.address_state,
                "zip_code": self.address_zip_code,
                "reference": self.address_reference,
                "lat": self.address_lat,
                "lng": self.address_lng,
            },
            "driver_id": self.driver_id,
            "vehicle_id": self.vehicle_id,
            "route_id": self.route_id,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "arrived_at": self.arrived_at.isoformat() if self.arrived_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "failed_reason": self.failed_reason,
            "failure_notes": self.failure_notes,
            "proof_type": self.proof_type,
            "notes": self.notes,
            "driver_notes": self.driver_notes,
            "timeline": self.timeline or [],
        }


class DriverLocationRecord(Base):
    """Persistent driver GPS location — replaces in-memory locations store."""

    __tablename__ = "driver_locations"

    __table_args__ = (Index("ix_driver_loc_tenant_driver", "tenant_id", "driver_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, default="default", nullable=False)
    driver_id = Column(String(36), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    accuracy = Column(Float, nullable=True)
    speed = Column(Float, nullable=True)
    bearing = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_stale = Column(Boolean, default=False)


class OutboxEntry(Base):
    """Event outbox — guarantees at-least-once event delivery."""

    __tablename__ = "outbox_entries"

    __table_args__ = (
        Index("ix_outbox_status", "status", "created_at"),
        Index("ix_outbox_tenant", "tenant_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(100), nullable=False)
    tenant_id = Column(String, default="default", nullable=False)
    aggregate_id = Column(String(36), nullable=False)
    actor_id = Column(String(36), default="")
    actor_type = Column(String(20), default="SYSTEM")
    payload = Column(JSON, nullable=False)
    status = Column(String(20), default="PENDING")  # PENDING, PROCESSED, FAILED
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)


class DriverSessionRecord(Base):
    """Persistent driver session — replaces in-memory sessions store."""

    __tablename__ = "driver_sessions"

    __table_args__ = (
        UniqueConstraint("token", name="uq_driver_session_token"),
        Index("ix_driver_session_driver", "driver_id"),
        Index("ix_driver_session_tenant", "tenant_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(200), nullable=False)
    driver_id = Column(String(36), nullable=False)
    tenant_id = Column(String, default="default", nullable=False)
    role = Column(String(20), default="DRIVER")
    device_id = Column(String(100), nullable=True)
    device_name = Column(String(100), nullable=True)
    platform = Column(String(50), nullable=True)
    status = Column(String(20), default="ACTIVE")  # ACTIVE, REVOKED, EXPIRED
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "token": self.token,
            "driver_id": self.driver_id,
            "tenant_id": self.tenant_id,
            "role": self.role,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "platform": self.platform,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class IdempotencyKeyRecord(Base):
    """Persistent idempotency key — replaces in-memory idempotency store."""

    __tablename__ = "idempotency_keys"

    __table_args__ = (
        UniqueConstraint("key", name="uq_idempotency_key"),
        Index("ix_idempotency_tenant", "tenant_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(200), nullable=False)
    tenant_id = Column(String, default="default", nullable=False)
    result_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
