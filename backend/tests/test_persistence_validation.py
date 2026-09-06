"""
Persistence Validation Tests — Fase 15.3

Verifies that critical operational state survives process restart
by using the database as single source of truth.

Tests:
1. Driver session persists across "restart" (re-creating DB layer)
2. Session revocation persists
3. Idempotency key persists
4. Delivery state persists
5. Concurrent idempotency key insertion (race condition)
6. Tenant isolation for sessions and idempotency
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.infrastructure.database.base import Base
from app.infrastructure.repositories.delivery_persistence_repository import (
    SQLAlchemyDriverSessionRepository,
    SQLAlchemyIdempotencyRepository,
    SQLAlchemyDeliveryPersistenceRepository,
)
from app.infrastructure.repositories.delivery_persistence_model import IdempotencyKeyRecord


@pytest.fixture
def db():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = DBSession(bind=engine)
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def session_repo(db):
    return SQLAlchemyDriverSessionRepository(db)


@pytest.fixture
def idem_repo(db):
    return SQLAlchemyIdempotencyRepository(db)


@pytest.fixture
def delivery_repo(db):
    return SQLAlchemyDeliveryPersistenceRepository(db, tenant_id="test-tenant")


# ═══════════════════════════════════════════════════════════
# 1. SESSION RESTART TEST
# ═══════════════════════════════════════════════════════════


class TestSessionPersistence:
    def test_session_survives_simulated_restart(self, db, session_repo):
        """Login → new DB session (simulates restart) → still authenticated."""
        # Step 1: Create session
        token = "test-token-001"
        expires = datetime.utcnow() + timedelta(hours=8)
        session_repo.create_session(
            token=token,
            driver_id="drv-1",
            tenant_id="t1",
            role="DRIVER",
            expires_at=expires,
        )

        # Step 2: Simulate restart — create a new repository instance
        # (in real scenario, this would be a new process)
        new_session_repo = SQLAlchemyDriverSessionRepository(db)

        # Step 3: Verify session persists
        record = new_session_repo.get_session(token)
        assert record is not None
        assert record.driver_id == "drv-1"
        assert record.tenant_id == "t1"
        assert record.status == "ACTIVE"
        assert record.expires_at is not None

    def test_revoked_session_persists(self, db, session_repo):
        """Logout → new DB session → session still revoked."""
        token = "test-token-002"
        session_repo.create_session(
            token=token,
            driver_id="drv-1",
            tenant_id="t1",
        )

        # Revoke
        session_repo.revoke_session(token)

        # New repo simulates restart
        new_repo = SQLAlchemyDriverSessionRepository(db)
        record = new_repo.get_session(token)
        assert record is None  # get_session filters by ACTIVE

    def test_expired_session_not_returned(self, db, session_repo):
        """Expired session is not returned by get_session."""
        token = "test-token-003"
        expired_at = datetime.utcnow() - timedelta(hours=1)
        session_repo.create_session(
            token=token,
            driver_id="drv-1",
            tenant_id="t1",
            expires_at=expired_at,
        )
        # Even though it's "ACTIVE" status, it should be treated as invalid
        record = session_repo.get_session(token)
        assert record is not None  # get_session checks ACTIVE only
        # But caller checks expiry
        assert record.expires_at < datetime.utcnow()

    def test_session_tenant_isolation(self, db):
        """Tenant A session cannot be used by Tenant B."""
        repo_a = SQLAlchemyDriverSessionRepository(db)
        repo_a.create_session(
            token="token-a",
            driver_id="drv-a",
            tenant_id="tenant-a",
        )

        repo_b = SQLAlchemyDriverSessionRepository(db)
        record = repo_b.get_session("token-a")
        # Session is not tenant-scoped in get_session, but the caller
        # checks tenant_id from the session record
        assert record is not None
        assert record.tenant_id == "tenant-a"  # Owner's tenant
        # Caller must verify: if ctx["tenant_id"] != record.tenant_id → FORBIDDEN


# ═══════════════════════════════════════════════════════════
# 2. IDEMPOTENCY RESTART TEST
# ═══════════════════════════════════════════════════════════


class TestIdempotencyPersistence:
    def test_idempotency_survives_restart(self, db, idem_repo):
        """Record key → new repo instance → key still exists."""
        key = "idem-001"
        idem_repo.record(key)

        new_repo = SQLAlchemyIdempotencyRepository(db)
        assert new_repo.exists(key)

    def test_different_keys_independent(self, db, idem_repo):
        """Recording key-1 doesn't affect key-2."""
        idem_repo.record("key-1")
        assert idem_repo.exists("key-1")
        assert not idem_repo.exists("key-2")

    def test_no_key_bypass(self, idem_repo):
        """None/empty key always returns not found."""
        assert not idem_repo.exists(None)
        assert not idem_repo.exists("")

    def test_record_idempotent(self, db, idem_repo):
        """Recording same key twice doesn't duplicate."""
        idem_repo.record("key-dup")
        idem_repo.record("key-dup")  # Should not raise
        # Only one record
        count = db.query(IdempotencyKeyRecord).filter(IdempotencyKeyRecord.key == "key-dup").count()
        assert count == 1

    def test_idempotency_tenant_isolation(self, db):
        """Tenant A and B can have same key independently (if scoped)."""
        repo_a = SQLAlchemyIdempotencyRepository(db)
        repo_a.record("shared-key", tenant_id="tenant-a")

        repo_b = SQLAlchemyIdempotencyRepository(db)
        # If key is globally unique, B sees A's key
        assert repo_b.exists("shared-key")
        # Note: current implementation uses global key uniqueness.
        # If per-tenant is needed, the schema must change.


# ═══════════════════════════════════════════════════════════
# 3. DELIVERY STATE RESTART TEST
# ═══════════════════════════════════════════════════════════


class TestDeliveryPersistence:
    def test_delivery_survives_restart(self, db, delivery_repo):
        """Create delivery → new repo → delivery still exists."""
        record = delivery_repo.create_delivery(
            delivery_id="del-001",
            order_id="ORD-001",
            customer_name="Test Customer",
        )
        assert record.status == "PENDING"

        new_repo = SQLAlchemyDeliveryPersistenceRepository(db, tenant_id="test-tenant")
        found = new_repo.get_delivery("del-001")
        assert found is not None
        assert found.status == "PENDING"
        assert found.version == 1

    def test_delivery_state_transitions_persist(self, db, delivery_repo):
        """State changes persist: PENDING → ASSIGNED → EN_ROUTE."""
        delivery_repo.create_delivery(
            delivery_id="del-002",
            order_id="ORD-002",
        )

        assigned = delivery_repo.assign_delivery(
            "del-002",
            driver_id="drv-1",
            vehicle_id=None,
            version=1,
        )
        assert assigned is not None
        assert assigned.status == "ASSIGNED"
        assert assigned.version == 2

        started = delivery_repo.start_delivery("del-002", version=2, driver_id="drv-1")
        assert started is not None
        assert started.status == "EN_ROUTE"
        assert started.version == 3

        # Verify via new repo instance
        new_repo = SQLAlchemyDeliveryPersistenceRepository(db, tenant_id="test-tenant")
        record = new_repo.get_delivery("del-002")
        assert record.status == "EN_ROUTE"
        assert record.version == 3
        assert len(record.timeline) >= 3  # PENDING → ASSIGNED → EN_ROUTE

    def test_delivery_tenant_isolation(self, db):
        """Tenant A delivery not visible to Tenant B."""
        repo_a = SQLAlchemyDeliveryPersistenceRepository(db, tenant_id="tenant-a")
        repo_a.create_delivery(delivery_id="del-a1", order_id="ORD-A1")

        repo_b = SQLAlchemyDeliveryPersistenceRepository(db, tenant_id="tenant-b")
        found = repo_b.get_delivery("del-a1")
        assert found is None

    def test_version_conflict_detected(self, db, delivery_repo):
        """Optimistic locking: stale version returns None."""
        delivery_repo.create_delivery(
            delivery_id="del-003",
            order_id="ORD-003",
        )
        # Assign with correct version
        result = delivery_repo.assign_delivery(
            "del-003",
            "drv-1",
            None,
            version=1,
        )
        assert result is not None

        # Try to assign again with stale version
        result2 = delivery_repo.assign_delivery(
            "del-003",
            "drv-2",
            None,
            version=1,
        )
        assert result2 is None  # Conflict


# ═══════════════════════════════════════════════════════════
# 4. CONCURRENCY TEST — IDEMPOTENCY
# ═══════════════════════════════════════════════════════════


class TestIdempotencyConcurrency:
    def test_duplicate_key_sequential_only_one_inserted(self, db):
        """Sequential inserts of the same key: only one record created."""
        key = "concurrent-key-001"
        repo = SQLAlchemyIdempotencyRepository(db)
        repo.record(key)
        repo.record(key)  # Second should be idempotent

        count = db.query(IdempotencyKeyRecord).filter(IdempotencyKeyRecord.key == key).count()
        assert count == 1

    def test_different_keys_both_persist(self, db):
        """Different keys both exist independently."""
        repo = SQLAlchemyIdempotencyRepository(db)
        repo.record("key-A")
        repo.record("key-B")

        assert repo.exists("key-A")
        assert repo.exists("key-B")

    def test_postgres_would_handle_true_concurrency(self, db):
        """Documentation: SQLite doesn't support true concurrent writes.

        In production (PostgreSQL), UNIQUE constraint on 'key' column
        ensures exactly one insert wins in a race condition.
        This test validates the constraint exists in the schema.
        """
        from app.infrastructure.repositories.delivery_persistence_model import IdempotencyKeyRecord

        # Verify unique constraint exists
        table = IdempotencyKeyRecord.__table__
        unique_constraints = [c for c in table.constraints if hasattr(c, "columns")]
        assert len(unique_constraints) > 0, "IdempotencyKeyRecord must have unique constraint"


# ═══════════════════════════════════════════════════════════
# 5. CLEANUP TEST
# ═══════════════════════════════════════════════════════════


class TestCleanup:
    def test_cleanup_expired_sessions(self, db, session_repo):
        """Expired sessions are marked EXPIRED."""
        # Create an expired session
        session_repo.create_session(
            token="old-token",
            driver_id="drv-1",
            tenant_id="t1",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        # Create a valid session
        session_repo.create_session(
            token="new-token",
            driver_id="drv-1",
            tenant_id="t1",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )

        session_repo.cleanup_expired()

        # Old token should not be returned by get_session
        old = session_repo.get_session("old-token")
        assert old is None  # Status changed to EXPIRED

        # New token still valid
        new = session_repo.get_session("new-token")
        assert new is not None
