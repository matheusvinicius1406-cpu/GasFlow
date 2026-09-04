"""
Delivery Persistence Tests — Tests for DB-backed delivery lifecycle.

Covers:
- Delivery CRUD + state machine
- GPS location persistence + stale detection
- Outbox pattern
- Version conflicts (optimistic locking)
- Tenant isolation
- Idempotency
"""

import gc
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database.base import Base
from app.infrastructure.repositories.delivery_persistence_model import (
    DriverLocationRecord, OutboxEntry,
)
from app.infrastructure.repositories.delivery_persistence_repository import (
    SQLAlchemyDeliveryPersistenceRepository,
    SQLAlchemyDriverLocationRepository,
    SQLAlchemyOutboxRepository,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def set_pragma(c, _):
        cur = c.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    gc.collect()
    engine.dispose()


# ═══════════════════════════════════════════════════════════
# DELIVERY CRUD
# ═══════════════════════════════════════════════════════════

class TestDeliveryCRUD:
    def test_create_delivery(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        record = repo.create_delivery(
            delivery_id="del-001",
            order_id="ord-001",
            customer_codigo="000001",
            customer_name="João Silva",
            address={"street": "Rua A", "number": "123", "neighborhood": "Centro"},
        )
        assert record.delivery_id == "del-001"
        assert record.status == "PENDING"
        assert record.version == 1
        assert record.address_street == "Rua A"

    def test_get_delivery(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        repo.create_delivery(delivery_id="del-002", order_id="ord-002")
        record = repo.get_delivery("del-002")
        assert record is not None
        assert record.delivery_id == "del-002"

    def test_get_nonexistent_delivery(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        record = repo.get_delivery("nonexistent")
        assert record is None

    def test_list_deliveries(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        for i in range(5):
            repo.create_delivery(delivery_id=f"del-{i:03d}", order_id=f"ord-{i:03d}")
        records = repo.list_deliveries()
        assert len(records) == 5

    def test_list_deliveries_by_status(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        r1 = repo.create_delivery(delivery_id="del-010", order_id="ord-010")
        r2 = repo.create_delivery(delivery_id="del-011", order_id="ord-011")
        repo.assign_delivery("del-010", "driver1", None, r1.version)
        pending = repo.list_deliveries(status="PENDING")
        assigned = repo.list_deliveries(status="ASSIGNED")
        assert len(pending) == 1
        assert len(assigned) == 1

    def test_list_deliveries_by_driver(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        r1 = repo.create_delivery(delivery_id="del-020", order_id="ord-020")
        r2 = repo.create_delivery(delivery_id="del-021", order_id="ord-021")
        repo.assign_delivery("del-020", "driver1", None, r1.version)
        repo.assign_delivery("del-021", "driver2", None, r2.version)
        driver1_deliveries = repo.list_by_driver("driver1")
        driver2_deliveries = repo.list_by_driver("driver2")
        assert len(driver1_deliveries) == 1
        assert len(driver2_deliveries) == 1

    def test_count_by_status(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        r1 = repo.create_delivery(delivery_id="del-030", order_id="ord-030")
        r2 = repo.create_delivery(delivery_id="del-031", order_id="ord-031")
        repo.assign_delivery("del-030", "driver1", None, r1.version)
        counts = repo.count_by_status()
        assert counts.get("PENDING", 0) == 1
        assert counts.get("ASSIGNED", 0) == 1

    def test_to_dict(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        record = repo.create_delivery(delivery_id="del-040", order_id="ord-040")
        d = record.to_dict()
        assert d["id"] == "del-040"
        assert d["status"] == "PENDING"
        assert "address" in d
        assert "timeline" in d


# ═══════════════════════════════════════════════════════════
# STATE MACHINE
# ═══════════════════════════════════════════════════════════

class TestStateMachine:
    def test_happy_path(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        r = repo.create_delivery(delivery_id="del-100", order_id="ord-100")
        assert r.status == "PENDING"

        r = repo.assign_delivery("del-100", "driver1", None, r.version)
        assert r.status == "ASSIGNED"
        assert r.driver_id == "driver1"

        r = repo.start_delivery("del-100", r.version, "driver1")
        assert r.status == "EN_ROUTE"

        r = repo.arrive_delivery("del-100", r.version)
        assert r.status == "ARRIVED"

        r = repo.complete_delivery("del-100", r.version)
        assert r.status == "DELIVERED"

    def test_fail_flow(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        r = repo.create_delivery(delivery_id="del-110", order_id="ord-110")
        r = repo.assign_delivery("del-110", "driver1", None, r.version)
        r = repo.start_delivery("del-110", r.version, "driver1")
        r = repo.fail_delivery("del-110", r.version, reason="CUSTOMER_ABSENT", notes="Não em casa")
        assert r.status == "FAILED"
        assert r.failed_reason == "CUSTOMER_ABSENT"

    def test_cancel_flow(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        r = repo.create_delivery(delivery_id="del-120", order_id="ord-120")
        r = repo.cancel_delivery("del-120", r.version)
        assert r.status == "CANCELLED"

    def test_version_conflict(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        r = repo.create_delivery(delivery_id="del-130", order_id="ord-130")
        old_version = r.version  # Capture version before first transition
        # First transition succeeds
        repo.assign_delivery("del-130", "driver1", None, old_version)
        # Second transition with old version should fail
        result = repo.assign_delivery("del-130", "driver2", None, old_version)
        assert result is None  # Version conflict

    def test_timeline_recorded(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        r = repo.create_delivery(delivery_id="del-140", order_id="ord-140")
        r = repo.assign_delivery("del-140", "driver1", None, r.version)
        r = repo.start_delivery("del-140", r.version, "driver1")
        record = repo.get_delivery("del-140")
        assert len(record.timeline) >= 3  # PENDING, ASSIGNED, EN_ROUTE

    def test_timestamps_set(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        r = repo.create_delivery(delivery_id="del-150", order_id="ord-150")
        assert r.created_at is not None
        r = repo.assign_delivery("del-150", "driver1", None, r.version)
        assert r.assigned_at is not None
        r = repo.start_delivery("del-150", r.version, "driver1")
        assert r.started_at is not None
        r = repo.arrive_delivery("del-150", r.version)
        assert r.arrived_at is not None
        r = repo.complete_delivery("del-150", r.version)
        assert r.delivered_at is not None


# ═══════════════════════════════════════════════════════════
# TENANT ISOLATION
# ═══════════════════════════════════════════════════════════

class TestTenantIsolation:
    def test_cross_tenant_invisible(self, db):
        repo_a = SQLAlchemyDeliveryPersistenceRepository(db, "tenant_a")
        repo_b = SQLAlchemyDeliveryPersistenceRepository(db, "tenant_b")
        repo_a.create_delivery(delivery_id="del-200", order_id="ord-200")
        assert repo_a.get_delivery("del-200") is not None
        assert repo_b.get_delivery("del-200") is None

    def test_cross_tenant_list(self, db):
        repo_a = SQLAlchemyDeliveryPersistenceRepository(db, "tenant_a")
        repo_b = SQLAlchemyDeliveryPersistenceRepository(db, "tenant_b")
        repo_a.create_delivery(delivery_id="del-210", order_id="ord-210")
        repo_b.create_delivery(delivery_id="del-211", order_id="ord-211")
        assert len(repo_a.list_deliveries()) == 1
        assert len(repo_b.list_deliveries()) == 1


# ═══════════════════════════════════════════════════════════
# GPS LOCATION
# ═══════════════════════════════════════════════════════════

class TestGPSLocation:
    def test_upsert_location(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        loc = repo.upsert_location("default", "driver1", -23.55, -46.63, accuracy=10.0)
        assert loc.latitude == -23.55
        assert loc.longitude == -46.63

    def test_update_location(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        repo.upsert_location("default", "driver1", -23.55, -46.63)
        repo.upsert_location("default", "driver1", -23.56, -46.64)
        loc = repo.get_location("default", "driver1")
        assert loc.latitude == -23.56

    def test_get_all_locations(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        repo.upsert_location("default", "driver1", -23.55, -46.63)
        repo.upsert_location("default", "driver2", -23.56, -46.64)
        locations = repo.get_all_locations("default")
        assert len(locations) == 2

    def test_stale_detection(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        # Create old location
        repo.upsert_location("default", "driver1", -23.55, -46.63)
        # Manually age it
        loc = db.query(DriverLocationRecord).first()
        loc.timestamp = datetime.utcnow() - timedelta(seconds=600)
        db.commit()
        # Check stale detection
        locations = repo.get_all_locations("default", stale_threshold_seconds=300)
        assert len(locations) == 1
        assert locations[0]["is_stale"] is True

    def test_fresh_location_not_stale(self, db):
        repo = SQLAlchemyDriverLocationRepository(db)
        repo.upsert_location("default", "driver1", -23.55, -46.63)
        locations = repo.get_all_locations("default", stale_threshold_seconds=300)
        assert len(locations) == 1
        assert locations[0]["is_stale"] is False


# ═══════════════════════════════════════════════════════════
# OUTBOX
# ═══════════════════════════════════════════════════════════

class TestOutbox:
    def test_enqueue_event(self, db):
        repo = SQLAlchemyOutboxRepository(db)
        entry = repo.enqueue(
            event_type="delivery.completed",
            tenant_id="default",
            aggregate_id="del-300",
            payload={"delivery_id": "del-300", "status": "DELIVERED"},
        )
        assert entry.id is not None
        assert entry.status == "PENDING"

    def test_get_pending(self, db):
        repo = SQLAlchemyOutboxRepository(db)
        repo.enqueue("delivery.completed", "default", "del-301", {"x": 1})
        repo.enqueue("delivery.failed", "default", "del-302", {"x": 2})
        pending = repo.get_pending()
        assert len(pending) == 2

    def test_mark_processed(self, db):
        repo = SQLAlchemyOutboxRepository(db)
        entry = repo.enqueue("delivery.completed", "default", "del-303", {"x": 1})
        repo.mark_processed(entry.id)
        pending = repo.get_pending()
        assert len(pending) == 0

    def test_mark_failed(self, db):
        repo = SQLAlchemyOutboxRepository(db)
        entry = repo.enqueue("delivery.completed", "default", "del-304", {"x": 1})
        repo.mark_failed(entry.id, "Connection refused")
        pending = repo.get_pending()
        assert len(pending) == 1  # Still pending, retryable

    def test_max_retries(self, db):
        repo = SQLAlchemyOutboxRepository(db)
        entry = repo.enqueue("delivery.completed", "default", "del-305", {"x": 1})
        for _ in range(3):
            repo.mark_failed(entry.id, "error")
        pending = repo.get_pending()
        assert len(pending) == 0  # Moved to FAILED
        failed = db.query(OutboxEntry).filter(OutboxEntry.status == "FAILED").all()
        assert len(failed) == 1


# ═══════════════════════════════════════════════════════════
# ALLOWED ACTIONS
# ═══════════════════════════════════════════════════════════

class TestAllowedActions:
    def test_pending_actions(self):
        actions = SQLAlchemyDeliveryPersistenceRepository.allowed_actions("PENDING")
        assert actions["can_accept"] is True
        assert actions["can_start"] is False

    def test_assigned_actions(self):
        actions = SQLAlchemyDeliveryPersistenceRepository.allowed_actions("ASSIGNED")
        assert actions["can_accept"] is False
        assert actions["can_start"] is True

    def test_en_route_actions(self):
        actions = SQLAlchemyDeliveryPersistenceRepository.allowed_actions("EN_ROUTE")
        assert actions["can_arrive"] is True
        assert actions["can_fail"] is True

    def test_delivered_actions(self):
        actions = SQLAlchemyDeliveryPersistenceRepository.allowed_actions("DELIVERED")
        assert actions["can_accept"] is False
        assert actions["can_start"] is False
        assert actions["can_complete"] is False


# ═══════════════════════════════════════════════════════════
# IDEMPOTENCY
# ═══════════════════════════════════════════════════════════

class TestIdempotency:
    def test_create_idempotent_key(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        r1 = repo.create_delivery(delivery_id="del-400", order_id="ord-400", idempotency_key="idem-1")
        assert r1.idempotency_key == "idem-1"

    def test_duplicate_delivery_id(self, db):
        repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        repo.create_delivery(delivery_id="del-401", order_id="ord-401")
        with pytest.raises(Exception):
            repo.create_delivery(delivery_id="del-401", order_id="ord-402")
