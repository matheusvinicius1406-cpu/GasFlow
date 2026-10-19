"""Route Plan Persistence Tests (A4) — plano otimizado persistido em SQLite.

Covers:
- save_plan upsert (plan_version incrementa, campos atualizados)
- get_latest devolve o plano correto (tenant-scoped)
- Isolamento entre tenants
- Sobrevive a "restart" (nova sessão, mesmo arquivo/DB file via StaticPool)
- geometry JSON round-trip
- delete_for_driver limpa o plano
- changed snapshot calculado corretamente
"""

import gc
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.routing.optimizer import OptimizedRoute
from app.infrastructure.database.base import Base
from app.infrastructure.repositories.route_plan_repository import SQLAlchemyRoutePlanRepository


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

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


def _plan(
    ordered_ids=None,
    distance=12.5,
    duration=3600,
    improvement=2.0,
    provider="haversine",
    geometry=None,
):
    return OptimizedRoute(
        ordered_delivery_ids=ordered_ids or ["d1", "d2", "d3"],
        total_distance_km=distance,
        total_duration_s=duration,
        geometry=geometry,
        improvement_km=improvement,
        provider=provider,
    )


class TestRoutePlanSave:
    def test_save_new_plan(self, db):
        repo = SQLAlchemyRoutePlanRepository(db, "default")
        record = repo.save_plan(driver_id="drv-1", plan=_plan())
        assert record.tenant_id == "default"
        assert record.driver_id == "drv-1"
        assert record.plan_version == 1
        assert record.ordered_delivery_ids == ["d1", "d2", "d3"]
        assert record.source == "ENDPOINT"
        assert record.changed == 0  # input=None → changed=0

    def test_save_upsert_increments_version(self, db):
        repo = SQLAlchemyRoutePlanRepository(db, "default")
        r1 = repo.save_plan(driver_id="drv-1", plan=_plan())
        r2 = repo.save_plan(
            driver_id="drv-1",
            plan=_plan(ordered_ids=["d3", "d1", "d2"], improvement=3.1),
            source="ASSIGN",
        )
        assert r2.id == r1.id  # mesma linha (upsert)
        assert r2.plan_version == 2
        assert r2.source == "ASSIGN"
        assert r2.improvement_km == 3.1

    def test_save_with_input_ids_computes_changed(self, db):
        repo = SQLAlchemyRoutePlanRepository(db, "default")
        record = repo.save_plan(
            driver_id="drv-1",
            plan=_plan(ordered_ids=["d2", "d1", "d3"]),
            input_delivery_ids=["d1", "d2", "d3"],
        )
        assert record.changed == 1
        record2 = repo.save_plan(
            driver_id="drv-2",
            plan=_plan(ordered_ids=["a", "b"]),
            input_delivery_ids=["a", "b"],
        )
        assert record2.changed == 0

    def test_save_persists_geometry(self, db):
        geometry = [(-1.45, -48.50), (-1.46, -48.51)]
        repo = SQLAlchemyRoutePlanRepository(db, "default")
        record = repo.save_plan(driver_id="drv-1", plan=_plan(geometry=geometry))
        assert record.geometry == [list(p) for p in geometry]

    def test_save_persists_origin(self, db):
        repo = SQLAlchemyRoutePlanRepository(db, "default")
        record = repo.save_plan(driver_id="drv-1", plan=_plan(), origin=(-1.45, -48.50))
        assert record.origin_lat == pytest.approx(-1.45)
        assert record.origin_lng == pytest.approx(-48.50)


class TestRoutePlanRead:
    def test_get_latest(self, db):
        repo = SQLAlchemyRoutePlanRepository(db, "default")
        repo.save_plan(driver_id="drv-1", plan=_plan())
        record = repo.get_latest("drv-1")
        assert record is not None
        assert record.driver_id == "drv-1"

    def test_get_latest_returns_none_for_unknown_driver(self, db):
        repo = SQLAlchemyRoutePlanRepository(db, "default")
        assert repo.get_latest("nobody") is None

    def test_list_by_tenant(self, db):
        repo = SQLAlchemyRoutePlanRepository(db, "default")
        repo.save_plan(driver_id="drv-1", plan=_plan())
        repo.save_plan(driver_id="drv-2", plan=_plan())
        plans = repo.list_by_tenant()
        assert len(plans) == 2

    def test_delete_for_driver(self, db):
        repo = SQLAlchemyRoutePlanRepository(db, "default")
        repo.save_plan(driver_id="drv-1", plan=_plan())
        deleted = repo.delete_for_driver("drv-1")
        assert deleted == 1
        assert repo.get_latest("drv-1") is None


class TestRoutePlanTenantIsolation:
    def test_tenant_a_cannot_see_tenant_b(self, db):
        repo_a = SQLAlchemyRoutePlanRepository(db, "tenant-a")
        repo_b = SQLAlchemyRoutePlanRepository(db, "tenant-b")
        repo_a.save_plan(driver_id="drv-1", plan=_plan())
        record_b = repo_b.get_latest("drv-1")
        assert record_b is None

    def test_list_by_tenant_is_scoped(self, db):
        repo_a = SQLAlchemyRoutePlanRepository(db, "tenant-a")
        repo_b = SQLAlchemyRoutePlanRepository(db, "tenant-b")
        repo_a.save_plan(driver_id="drv-1", plan=_plan())
        repo_b.save_plan(driver_id="drv-2", plan=_plan())
        assert len(repo_a.list_by_tenant()) == 1
        assert len(repo_b.list_by_tenant()) == 1


class TestRoutePlanRestartSurvival:
    def test_plan_survives_session_restart(self, db):
        repo = SQLAlchemyRoutePlanRepository(db, "default")
        record = repo.save_plan(driver_id="drv-1", plan=_plan(ordered_ids=["x", "y"]))

        # Simula restart: nova sessão no mesmo engine.
        Session = sessionmaker(bind=db.get_bind())
        new_session = Session()
        try:
            repo2 = SQLAlchemyRoutePlanRepository(new_session, "default")
            loaded = repo2.get_latest("drv-1")
            assert loaded is not None
            assert loaded.id == record.id
            assert loaded.ordered_delivery_ids == ["x", "y"]
            assert loaded.plan_version == 1
        finally:
            new_session.close()


class TestRoutePlanSchema:
    def test_all_expected_columns(self, db):
        repo = SQLAlchemyRoutePlanRepository(db, "default")
        record = repo.save_plan(driver_id="drv-1", plan=_plan())
        assert record.id  # uuid gerado
        uuid.UUID(record.id)  # deve ser uuid válido
        assert record.created_at is not None
        assert record.total_duration_s == 3600
        assert record.provider == "haversine"
