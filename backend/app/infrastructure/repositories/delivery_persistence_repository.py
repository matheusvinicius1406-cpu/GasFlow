"""
Delivery Persistence Repository — SQLAlchemy implementation.

Replaces the in-memory store with real database persistence.
Single source of truth for delivery lifecycle.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.infrastructure.repositories.delivery_persistence_model import (
    DeliveryRecord, DriverLocationRecord, OutboxEntry,
    DriverSessionRecord, IdempotencyKeyRecord
)
from app.infrastructure.repositories.tenant_mixin import TenantMixin


class SQLAlchemyDeliveryPersistenceRepository(TenantMixin):
    """Repository for delivery lifecycle persistence."""

    def __init__(self, db: Session, tenant_id: str = "default"):
        super().__init__(db, tenant_id)

    # ── Delivery CRUD ──────────────────────────────────

    def create_delivery(
        self,
        delivery_id: str,
        order_id: str,
        customer_codigo: str = "",
        customer_name: str = "",
        address: Optional[Dict] = None,
        notes: str = "",
        idempotency_key: Optional[str] = None,
    ) -> DeliveryRecord:
        """Create a new delivery record."""
        addr = address or {}
        record = DeliveryRecord(
            delivery_id=delivery_id,
            tenant_id=self.tenant_id,
            order_id=order_id,
            status="PENDING",
            version=1,
            customer_codigo=customer_codigo,
            customer_name=customer_name,
            address_street=addr.get("street", ""),
            address_number=addr.get("number", ""),
            address_complement=addr.get("complement", ""),
            address_neighborhood=addr.get("neighborhood", ""),
            address_city=addr.get("city", ""),
            address_state=addr.get("state", ""),
            address_zip_code=addr.get("zip_code", ""),
            address_reference=addr.get("reference", ""),
            address_lat=addr.get("lat"),
            address_lng=addr.get("lng"),
            notes=notes,
            idempotency_key=idempotency_key,
            timeline=[{
                "status": "PENDING",
                "timestamp": datetime.utcnow().isoformat(),
                "actor_type": "SYSTEM",
                "notes": "Delivery created",
            }],
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_delivery(self, delivery_id: str) -> Optional[DeliveryRecord]:
        return self._filter_by_tenant(DeliveryRecord).filter(
            DeliveryRecord.delivery_id == delivery_id
        ).first()

    def list_deliveries(
        self,
        status: Optional[str] = None,
        driver_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[DeliveryRecord]:
        q = self._filter_by_tenant(DeliveryRecord)
        if status:
            q = q.filter(DeliveryRecord.status == status)
        if driver_id:
            q = q.filter(DeliveryRecord.driver_id == driver_id)
        return q.order_by(DeliveryRecord.created_at.desc()).offset(offset).limit(limit).all()

    def count_by_status(self) -> Dict[str, int]:
        results = (
            self._filter_by_tenant(DeliveryRecord)
            .with_entities(DeliveryRecord.status, func.count())
            .group_by(DeliveryRecord.status)
            .all()
        )
        return {status: count for status, count in results}

    def list_by_driver(self, driver_id: str) -> List[DeliveryRecord]:
        return (
            self._filter_by_tenant(DeliveryRecord)
            .filter(DeliveryRecord.driver_id == driver_id)
            .order_by(DeliveryRecord.created_at.desc())
            .all()
        )

    def count_by_driver(self, driver_id: str) -> Dict[str, int]:
        results = (
            self._filter_by_tenant(DeliveryRecord)
            .filter(DeliveryRecord.driver_id == driver_id)
            .with_entities(DeliveryRecord.status, func.count())
            .group_by(DeliveryRecord.status)
            .all()
        )
        return {status: count for status, count in results}

    # ── State Transitions (version-locked) ─────────────

    def _transition(
        self, delivery_id: str, new_status: str,
        version: int, actor_type: str = "DRIVER",
        extra_fields: Optional[Dict] = None,
    ) -> Optional[DeliveryRecord]:
        """Atomic state transition with optimistic locking."""
        record = self._filter_by_tenant(DeliveryRecord).filter(
            DeliveryRecord.delivery_id == delivery_id,
            DeliveryRecord.version == version,
        ).first()

        if not record:
            return None

        record.status = new_status
        record.version = version + 1
        record.updated_at = datetime.utcnow()

        now = datetime.utcnow()
        if new_status == "ASSIGNED":
            record.assigned_at = now
        elif new_status == "EN_ROUTE":
            record.started_at = now
        elif new_status == "ARRIVED":
            record.arrived_at = now
        elif new_status == "DELIVERED":
            record.delivered_at = now
        elif new_status == "FAILED":
            record.failed_at = now

        if extra_fields:
            for key, value in extra_fields.items():
                if hasattr(record, key):
                    setattr(record, key, value)

        new_entry = {
            "status": new_status,
            "timestamp": now.isoformat(),
            "actor_type": actor_type,
        }
        if record.timeline:
            record.timeline = record.timeline + [new_entry]
        else:
            record.timeline = [new_entry]
        # Force SQLAlchemy to detect JSON change
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(record, "timeline")

        self.db.commit()
        self.db.refresh(record)
        return record

    def assign_delivery(
        self, delivery_id: str, driver_id: str, vehicle_id: Optional[str], version: int
    ) -> Optional[DeliveryRecord]:
        record = self._transition(delivery_id, "ASSIGNED", version, actor_type="OPERATOR")
        if record:
            record.driver_id = driver_id
            if vehicle_id:
                record.vehicle_id = vehicle_id
            self.db.commit()
        return record

    def start_delivery(self, delivery_id: str, version: int, driver_id: str) -> Optional[DeliveryRecord]:
        return self._transition(delivery_id, "EN_ROUTE", version, actor_type="DRIVER")

    def arrive_delivery(self, delivery_id: str, version: int) -> Optional[DeliveryRecord]:
        return self._transition(delivery_id, "ARRIVED", version, actor_type="DRIVER")

    def complete_delivery(
        self, delivery_id: str, version: int,
        proof_type: Optional[str] = None,
        proof_data: Optional[Dict] = None,
        driver_notes: str = "",
    ) -> Optional[DeliveryRecord]:
        extras = {}
        if proof_type:
            extras["proof_type"] = proof_type
        if proof_data:
            extras["proof_data"] = proof_data
        if driver_notes:
            extras["driver_notes"] = driver_notes
        return self._transition(delivery_id, "DELIVERED", version, actor_type="DRIVER",
                                extra_fields=extras or None)

    def fail_delivery(
        self, delivery_id: str, version: int,
        reason: str = "OTHER", notes: str = "",
    ) -> Optional[DeliveryRecord]:
        return self._transition(delivery_id, "FAILED", version, actor_type="DRIVER",
                                extra_fields={"failed_reason": reason, "failure_notes": notes})

    def cancel_delivery(self, delivery_id: str, version: int) -> Optional[DeliveryRecord]:
        return self._transition(delivery_id, "CANCELLED", version, actor_type="OPERATOR")

    # ── Allowed Actions ────────────────────────────────

    @staticmethod
    def allowed_actions(status: str) -> Dict[str, bool]:
        return {
            "can_accept": status == "PENDING",
            "can_start": status in ("ASSIGNED", "DISPATCHED"),
            "can_arrive": status == "EN_ROUTE",
            "can_complete": status == "ARRIVED",
            "can_fail": status in ("EN_ROUTE", "ARRIVED"),
        }


# ── GPS Location Repository ──────────────────────────────

class SQLAlchemyDriverLocationRepository:
    """Repository for driver GPS locations — replaces in-memory locations store."""

    def __init__(self, db: Session):
        self.db = db

    def upsert_location(
        self,
        tenant_id: str,
        driver_id: str,
        latitude: float,
        longitude: float,
        accuracy: Optional[float] = None,
        speed: Optional[float] = None,
        bearing: Optional[float] = None,
    ) -> DriverLocationRecord:
        """Insert or update driver location (latest wins)."""
        existing = (
            self.db.query(DriverLocationRecord)
            .filter(
                DriverLocationRecord.tenant_id == tenant_id,
                DriverLocationRecord.driver_id == driver_id,
            )
            .first()
        )

        now = datetime.utcnow()
        if existing:
            existing.latitude = latitude
            existing.longitude = longitude
            existing.accuracy = accuracy
            existing.speed = speed
            existing.bearing = bearing
            existing.timestamp = now
            existing.is_stale = False
        else:
            existing = DriverLocationRecord(
                tenant_id=tenant_id,
                driver_id=driver_id,
                latitude=latitude,
                longitude=longitude,
                accuracy=accuracy,
                speed=speed,
                bearing=bearing,
                timestamp=now,
            )
            self.db.add(existing)

        self.db.commit()
        self.db.refresh(existing)
        return existing

    def get_location(self, tenant_id: str, driver_id: str) -> Optional[DriverLocationRecord]:
        return (
            self.db.query(DriverLocationRecord)
            .filter(
                DriverLocationRecord.tenant_id == tenant_id,
                DriverLocationRecord.driver_id == driver_id,
            )
            .first()
        )

    def get_all_locations(self, tenant_id: str, stale_threshold_seconds: int = 300) -> List[Dict]:
        """Get all driver locations for admin map. Marks stale ones."""
        now = datetime.utcnow()
        records = (
            self.db.query(DriverLocationRecord)
            .filter(DriverLocationRecord.tenant_id == tenant_id)
            .all()
        )
        result = []
        for r in records:
            age = (now - r.timestamp).total_seconds()
            is_stale = age > stale_threshold_seconds
            if is_stale and not r.is_stale:
                r.is_stale = True
                self.db.commit()
            result.append({
                "driver_id": r.driver_id,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "accuracy": r.accuracy,
                "speed": r.speed,
                "bearing": r.bearing,
                "timestamp": r.timestamp.isoformat(),
                "is_stale": is_stale,
                "age_seconds": int(age),
            })
        return result

    def mark_stale(self, tenant_id: str, stale_threshold_seconds: int = 300):
        """Mark locations older than threshold as stale."""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(seconds=stale_threshold_seconds)
        self.db.query(DriverLocationRecord).filter(
            DriverLocationRecord.tenant_id == tenant_id,
            DriverLocationRecord.timestamp < cutoff,
            DriverLocationRecord.is_stale == False,
        ).update({"is_stale": True})
        self.db.commit()


# ── Outbox Repository ──────────────────────────────────

class SQLAlchemyOutboxRepository:
    """Repository for event outbox — guarantees at-least-once delivery."""

    def __init__(self, db: Session):
        self.db = db

    def enqueue(
        self,
        event_type: str,
        tenant_id: str,
        aggregate_id: str,
        payload: Dict[str, Any],
        actor_id: str = "",
        actor_type: str = "SYSTEM",
    ) -> OutboxEntry:
        """Insert event into outbox (within same DB transaction)."""
        entry = OutboxEntry(
            event_type=event_type,
            tenant_id=tenant_id,
            aggregate_id=aggregate_id,
            actor_id=actor_id,
            actor_type=actor_type,
            payload=payload,
            status="PENDING",
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def get_pending(self, limit: int = 100) -> List[OutboxEntry]:
        return (
            self.db.query(OutboxEntry)
            .filter(OutboxEntry.status == "PENDING")
            .order_by(OutboxEntry.created_at.asc())
            .limit(limit)
            .all()
        )

    def mark_processed(self, entry_id: int):
        entry = self.db.query(OutboxEntry).filter(OutboxEntry.id == entry_id).first()
        if entry:
            entry.status = "PROCESSED"
            entry.processed_at = datetime.utcnow()
            self.db.commit()

    def mark_failed(self, entry_id: int, error_message: str):
        entry = self.db.query(OutboxEntry).filter(OutboxEntry.id == entry_id).first()
        if entry:
            entry.retry_count += 1
            if entry.retry_count >= entry.max_retries:
                entry.status = "FAILED"
            entry.error_message = error_message
            self.db.commit()

    def cleanup_old(self, days: int = 7):
        """Remove old processed entries."""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        self.db.query(OutboxEntry).filter(
            OutboxEntry.status == "PROCESSED",
            OutboxEntry.processed_at < cutoff,
        ).delete()
        self.db.commit()


# ── Driver Session Repository ──────────────────────────

class SQLAlchemyDriverSessionRepository:
    """Repository for driver sessions — replaces in-memory sessions store."""

    def __init__(self, db: Session):
        self.db = db

    def create_session(
        self,
        token: str,
        driver_id: str,
        tenant_id: str,
        role: str = "DRIVER",
        device_id: Optional[str] = None,
        device_name: Optional[str] = None,
        platform: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> DriverSessionRecord:
        record = DriverSessionRecord(
            token=token,
            driver_id=driver_id,
            tenant_id=tenant_id,
            role=role,
            device_id=device_id,
            device_name=device_name,
            platform=platform,
            status="ACTIVE",
            expires_at=expires_at,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_session(self, token: str) -> Optional[DriverSessionRecord]:
        return self.db.query(DriverSessionRecord).filter(
            DriverSessionRecord.token == token,
            DriverSessionRecord.status == "ACTIVE",
        ).first()

    def revoke_session(self, token: str):
        record = self.db.query(DriverSessionRecord).filter(
            DriverSessionRecord.token == token
        ).first()
        if record:
            record.status = "REVOKED"
            self.db.commit()

    def revoke_all_for_driver(self, driver_id: str):
        self.db.query(DriverSessionRecord).filter(
            DriverSessionRecord.driver_id == driver_id,
            DriverSessionRecord.status == "ACTIVE",
        ).update({"status": "REVOKED"})
        self.db.commit()

    def cleanup_expired(self):
        from datetime import timedelta
        now = datetime.utcnow()
        self.db.query(DriverSessionRecord).filter(
            DriverSessionRecord.status == "ACTIVE",
            DriverSessionRecord.expires_at < now,
        ).update({"status": "EXPIRED"})
        self.db.commit()

    def to_dict(self, record: DriverSessionRecord) -> dict:
        return record.to_dict()


# ── Idempotency Key Repository ─────────────────────────

class SQLAlchemyIdempotencyRepository:
    """Repository for idempotency keys — replaces in-memory idempotency store."""

    def __init__(self, db: Session):
        self.db = db

    def exists(self, key: str) -> bool:
        return self.db.query(IdempotencyKeyRecord).filter(
            IdempotencyKeyRecord.key == key
        ).first() is not None

    def record(self, key: str, tenant_id: str = "default", result_json: Optional[Dict] = None):
        if self.exists(key):
            return
        record = IdempotencyKeyRecord(
            key=key,
            tenant_id=tenant_id,
            result_json=result_json,
        )
        self.db.add(record)
        self.db.commit()

    def cleanup_old(self, days: int = 7):
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        self.db.query(IdempotencyKeyRecord).filter(
            IdempotencyKeyRecord.created_at < cutoff,
        ).delete()
        self.db.commit()
