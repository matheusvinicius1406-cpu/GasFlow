"""
Delivery Persistence Repository — SQLAlchemy implementation.

Replaces the in-memory store with real database persistence.
Single source of truth for delivery lifecycle.
"""

import hashlib
import uuid

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.infrastructure.repositories.delivery_persistence_model import (
    DeliveryRecord,
    DriverLocationRecord,
    OutboxEntry,
    DriverSessionRecord,
    DriverRefreshTokenRecord,
    OfflineSyncLogRecord,
    IdempotencyKeyRecord,
)
from app.infrastructure.repositories.inventory_model import StockMovementModel
from app.infrastructure.repositories.tenant_mixin import TenantMixin
import logging

logger = logging.getLogger(__name__)


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
            timeline=[
                {
                    "status": "PENDING",
                    "timestamp": datetime.utcnow().isoformat(),
                    "actor_type": "SYSTEM",
                    "notes": "Delivery created",
                }
            ],
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_delivery(self, delivery_id: str) -> Optional[DeliveryRecord]:
        return self._filter_by_tenant(DeliveryRecord).filter(DeliveryRecord.delivery_id == delivery_id).first()

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
        self,
        delivery_id: str,
        new_status: str,
        version: int,
        actor_type: str = "DRIVER",
        extra_fields: Optional[Dict] = None,
    ) -> Optional[DeliveryRecord]:
        """Atomic state transition with optimistic locking."""
        record = (
            self._filter_by_tenant(DeliveryRecord)
            .filter(
                DeliveryRecord.delivery_id == delivery_id,
                DeliveryRecord.version == version,
            )
            .first()
        )

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

        # ── Decisão B3(a): débito de estoque na ENTREGA ──────
        # DELIVERED: debita a venda (quantity/quantity_full -= qty) e
        # credita os vazios devolvidos (quantity_empty += qty) — o fato
        # físico consumado. O pedido NÃO debita mais no CONFIRMED.
        # CANCELLED após DELIVERED: reverte o débito (estoque volta ao
        # estado pré-entrega). Reversão idempotente via movimento RETURN.
        # Best-effort: falha de estoque NUNCA reverte a transição de
        # entrega (a entrega é fato físico consumado); o erro é logado.
        try:
            self._apply_delivery_stock_effect(record)
        except Exception as exc:  # pragma: no cover — nunca derruba a transição
            logger.error(
                "falha ao aplicar efeito de estoque da entrega (delivery=%s status=%s): %s",
                delivery_id,
                new_status,
                exc,
            )

        return record

    def _apply_delivery_stock_effect(self, record: DeliveryRecord) -> None:
        """Aplica o débito da venda (DELIVERED) ou a reversão (CANCELLED pós-DELIVERED).

        Decisão B3(a): o pedido não debita mais no CONFIRMED — a entrega é
        o único ponto de débito. Idempotente por movimento:
        - DELIVERED → SALE com reference_type=DELIVERY (1x por entrega/produto)
        - CANCELLED pós-DELIVERED → RETURN com reference_type=DELIVERY (1x)
        """
        from collections import Counter

        from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository
        from app.infrastructure.repositories.order_item_model import OrderItemModel

        new_status = record.status
        if new_status not in ("DELIVERED", "CANCELLED"):
            return

        timeline_statuses = [e.get("status") for e in (record.timeline or []) if isinstance(e, dict)]
        was_delivered_before = "DELIVERED" in timeline_statuses[:-1]

        if new_status == "DELIVERED":
            # Idempotência: o débito já foi aplicado para esta entrega?
            existing = (
                self._filter_by_tenant(StockMovementModel)
                .filter(
                    StockMovementModel.reference_type == "DELIVERY",
                    StockMovementModel.reference_id == record.delivery_id,
                    StockMovementModel.type == "SALE",
                )
                .first()
            )
            if existing:
                return
        else:  # CANCELLED
            # Só reverte se a entrega estava DELIVERED antes do cancelamento.
            if not was_delivered_before:
                return
            existing_reversal = (
                self._filter_by_tenant(StockMovementModel)
                .filter(
                    StockMovementModel.reference_type == "DELIVERY",
                    StockMovementModel.reference_id == record.delivery_id,
                    StockMovementModel.type == "RETURN",
                )
                .first()
            )
            if existing_reversal:
                return

        # Itens do pedido vinculado — sem pedido/itens, nada a debitar.
        items = self.db.query(OrderItemModel).filter(OrderItemModel.order_codigo == record.order_id).all()
        if not items:
            return

        repo = SQLAlchemyInventoryRepository(self.db, self.tenant_id)
        quantities = Counter({i.product_codigo: i.quantity for i in items})
        for product_codigo, qty in quantities.items():
            if new_status == "DELIVERED":
                repo.deliver_stock_atomic(
                    product_codigo=product_codigo,
                    quantity=qty,
                    reason=f"Venda — entrega {record.delivery_id} (pedido #{record.order_id})",
                    reference_type="DELIVERY",
                    reference_id=record.delivery_id,
                )
            else:
                # CANCELLED após DELIVERED: devolve cheios ao estoque e
                # remove os vazios creditados (caminhão retorna os cilindros).
                repo.reverse_delivery_stock_atomic(
                    product_codigo=product_codigo,
                    quantity=qty,
                    reason=f"Reversão de venda — cancelamento entrega {record.delivery_id}",
                    reference_type="DELIVERY",
                    reference_id=record.delivery_id,
                )

        # ── F7: espelho no estoque do ENTREGADOR ────────────
        # DELIVERED: decrementa full_tanks_loaded do entregador (a base
        # já foi debitada acima — única vez). CANCELLED pós-DELIVERED:
        # devolve ao entregador o que a entrega consumiu. Best-effort:
        # nunca reverte/derruba a transição da entrega.
        if record.driver_id:
            try:
                from app.application.delivery.driver_stock_service import DriverStockService

                svc = DriverStockService(self.db, self.tenant_id)
                if new_status == "DELIVERED":
                    svc.apply_delivery_debit(record.driver_id, dict(quantities), record.delivery_id)
                else:
                    svc.reverse_delivery_debit(record.driver_id, dict(quantities), record.delivery_id)
            except Exception as exc:  # pragma: no cover — nunca derruba a transição
                logger.error(
                    "falha ao espelhar estoque do entregador (delivery=%s driver=%s): %s",
                    record.delivery_id,
                    record.driver_id,
                    exc,
                )

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
        self,
        delivery_id: str,
        version: int,
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
        return self._transition(delivery_id, "DELIVERED", version, actor_type="DRIVER", extra_fields=extras or None)

    def fail_delivery(
        self,
        delivery_id: str,
        version: int,
        reason: str = "OTHER",
        notes: str = "",
    ) -> Optional[DeliveryRecord]:
        return self._transition(
            delivery_id,
            "FAILED",
            version,
            actor_type="DRIVER",
            extra_fields={"failed_reason": reason, "failure_notes": notes},
        )

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
        records = self.db.query(DriverLocationRecord).filter(DriverLocationRecord.tenant_id == tenant_id).all()
        result = []
        for r in records:
            age = (now - r.timestamp).total_seconds()
            is_stale = age > stale_threshold_seconds
            if is_stale and not r.is_stale:
                r.is_stale = True
                self.db.commit()
            result.append(
                {
                    "driver_id": r.driver_id,
                    "latitude": r.latitude,
                    "longitude": r.longitude,
                    "accuracy": r.accuracy,
                    "speed": r.speed,
                    "bearing": r.bearing,
                    "timestamp": r.timestamp.isoformat(),
                    "is_stale": is_stale,
                    "age_seconds": int(age),
                }
            )
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


class SQLAlchemyDriverRefreshTokenRepository:
    """Refresh tokens do mobile — rotação com detecção de replay.

    Regras (prompt App do Entregador 7): rotação a cada uso; reuso de token
    já rotacionado revoga a família inteira.

    Os tokens são armazenados APENAS como hash SHA-256 (segurança: vazamento
    do banco não permite usar nem forjar sessões); as consultas recebem o
    token literal e hasheiam na entrada.
    """

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def __init__(self, db: Session):
        self.db = db

    def create_family(
        self, token: str, driver_id: str, tenant_id: str, expires_at: datetime
    ) -> DriverRefreshTokenRecord:
        record = DriverRefreshTokenRecord(
            token=self._hash(token),
            family_id=str(uuid.uuid4()),
            driver_id=driver_id,
            tenant_id=tenant_id,
            status="ACTIVE",
            expires_at=expires_at,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_active(self, token: str) -> Optional[DriverRefreshTokenRecord]:
        return (
            self.db.query(DriverRefreshTokenRecord)
            .filter(
                DriverRefreshTokenRecord.token == self._hash(token),
                DriverRefreshTokenRecord.status == "ACTIVE",
            )
            .first()
        )

    def get_any(self, token: str) -> Optional[DriverRefreshTokenRecord]:
        return (
            self.db.query(DriverRefreshTokenRecord).filter(DriverRefreshTokenRecord.token == self._hash(token)).first()
        )

    def rotate(
        self, old: DriverRefreshTokenRecord, new_token: str, new_expires_at: datetime
    ) -> DriverRefreshTokenRecord:
        """Marca o antigo como ROTATED e cria o novo na mesma família."""
        old.status = "ROTATED"
        record = DriverRefreshTokenRecord(
            token=self._hash(new_token),
            family_id=old.family_id,
            driver_id=old.driver_id,
            tenant_id=old.tenant_id,
            status="ACTIVE",
            expires_at=new_expires_at,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def revoke_family(self, family_id: str):
        self.db.query(DriverRefreshTokenRecord).filter(
            DriverRefreshTokenRecord.family_id == family_id,
            DriverRefreshTokenRecord.status.in_(("ACTIVE", "ROTATED")),
        ).update({"status": "REVOKED"}, synchronize_session=False)
        self.db.commit()

    def revoke_all_for_driver(self, driver_id: str):
        self.db.query(DriverRefreshTokenRecord).filter(
            DriverRefreshTokenRecord.driver_id == driver_id,
            DriverRefreshTokenRecord.status == "ACTIVE",
        ).update({"status": "REVOKED"}, synchronize_session=False)
        self.db.commit()


class SQLAlchemyOfflineSyncLogRepository:
    """Delta sync log — alimenta GET /driver/sync?since= do mobile."""

    def __init__(self, db: Session):
        self.db = db

    def record_change(self, tenant_id: str, entity_type: str, entity_id: str, action: str) -> None:
        self.db.add(
            OfflineSyncLogRecord(
                tenant_id=tenant_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
            )
        )
        self.db.commit()

    def changes_since(self, tenant_id: str, since: datetime, limit: int = 500) -> List[OfflineSyncLogRecord]:
        return (
            self.db.query(OfflineSyncLogRecord)
            .filter(
                OfflineSyncLogRecord.tenant_id == tenant_id,
                OfflineSyncLogRecord.changed_at > since,
            )
            .order_by(OfflineSyncLogRecord.changed_at.asc())
            .limit(limit)
            .all()
        )

    def purge_older_than(self, cutoff: datetime) -> int:
        deleted = (
            self.db.query(OfflineSyncLogRecord)
            .filter(OfflineSyncLogRecord.changed_at < cutoff)
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted


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
        return (
            self.db.query(DriverSessionRecord)
            .filter(
                DriverSessionRecord.token == token,
                DriverSessionRecord.status == "ACTIVE",
            )
            .first()
        )

    def revoke_session(self, token: str):
        record = self.db.query(DriverSessionRecord).filter(DriverSessionRecord.token == token).first()
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
        return self.db.query(IdempotencyKeyRecord).filter(IdempotencyKeyRecord.key == key).first() is not None

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
