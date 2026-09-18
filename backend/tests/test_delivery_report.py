"""Testes F9 — Agregados de entregas para os gráficos (ReportsPage).

Cobre:
- Série diária: criadas/entregues/falhas por dia.
- Por entregador: atribuídas/entregues/falhas + tempo médio (min).
- Por bairro: entregas DELIVERED.
- Janela inválida → 400; sempre filtrado por tenant.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.application.reports.delivery_metrics import delivery_report, VALID_DAYS
from app.infrastructure.database.base import Base
from app.infrastructure.repositories.delivery_persistence_model import DeliveryRecord


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _record(**kwargs) -> DeliveryRecord:
    defaults = dict(
        delivery_id=f"dlv-{datetime.utcnow().timestamp()}-{id(kwargs)}",
        tenant_id="default",
        order_id="O1",
        status="DELIVERED",
    )
    defaults.update(kwargs)
    return DeliveryRecord(**defaults)


class TestByDay:
    def test_counts_per_day(self, db):
        now = datetime.utcnow()
        db.add(_record(delivery_id="a", status="PENDING", created_at=now))
        d1 = now - timedelta(hours=2)
        db.add(_record(delivery_id="b", created_at=now, assigned_at=d1, delivered_at=now))
        db.add(_record(delivery_id="c", status="FAILED", created_at=now, failed_at=now))
        db.commit()

        report = delivery_report(db, "default", 30)
        today = [d for d in report["by_day"] if d["day"] == str(now.date())][0]
        assert today["created"] == 3
        assert today["delivered"] == 1
        assert today["failed"] == 1


class TestByDriver:
    def test_per_driver_with_avg_minutes(self, db):
        now = datetime.utcnow()
        assigned = now - timedelta(hours=2)
        db.add(
            _record(
                delivery_id="r1",
                driver_id="D1",
                created_at=now,
                assigned_at=assigned,
                delivered_at=now,  # 120 min
            )
        )
        db.add(
            _record(
                delivery_id="r2",
                driver_id="D1",
                created_at=now,
                assigned_at=assigned,
                delivered_at=now - timedelta(minutes=60),  # 60 min
            )
        )
        db.add(_record(delivery_id="r3", driver_id="D2", status="PENDING", created_at=now))
        db.commit()

        report = delivery_report(db, "default", 30)
        by_driver = {d["driver_id"]: d for d in report["by_driver"]}
        assert by_driver["D1"]["delivered"] == 2
        assert by_driver["D1"]["avg_minutes"] == pytest.approx(90.0)
        assert by_driver["D2"]["assigned"] == 1
        assert by_driver["D2"]["delivered"] == 0
        assert by_driver["D2"]["avg_minutes"] is None

    def test_ranking_sorted_by_delivered_desc(self, db):
        now = datetime.utcnow()
        for i in range(3):
            db.add(_record(delivery_id=f"a{i}", driver_id="MUITO", created_at=now))
        db.add(_record(delivery_id="b0", driver_id="POUCO", created_at=now))
        db.commit()

        report = delivery_report(db, "default", 30)
        delivered = [d["delivered"] for d in report["by_driver"]]
        assert delivered == sorted(delivered, reverse=True)


class TestByNeighborhood:
    def test_delivered_by_neighborhood(self, db):
        now = datetime.utcnow()
        db.add(_record(delivery_id="n1", address_neighborhood="Centro", created_at=now))
        db.add(_record(delivery_id="n2", address_neighborhood="Centro", created_at=now))
        db.add(_record(delivery_id="n3", address_neighborhood="Sul", created_at=now))
        db.commit()

        report = delivery_report(db, "default", 30)
        got = {n["neighborhood"]: n["count"] for n in report["by_neighborhood"]}
        assert got == {"Centro": 2, "Sul": 1}


class TestWindowAndTenant:
    def test_old_records_excluded(self, db):
        now = datetime.utcnow()
        db.add(_record(delivery_id="old", created_at=now - timedelta(days=60)))
        db.commit()

        report = delivery_report(db, "default", 30)
        assert report["by_day"] == []

    def test_tenant_isolation(self, db):
        now = datetime.utcnow()
        db.add(_record(delivery_id="x", tenant_id="other", created_at=now))
        db.commit()

        report = delivery_report(db, "default", 30)
        assert report["by_day"] == []

    def test_valid_days_constant(self):
        assert VALID_DAYS == (7, 30, 90)


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


class TestEndpoint:
    def test_get_report_ok(self, client, admin_headers):
        res = client.get("/reports/deliveries", params={"days": 30}, headers=admin_headers)
        assert res.status_code == 200
        body = res.json()
        assert {"by_day", "by_driver", "by_neighborhood", "days"} <= set(body)

    def test_invalid_window_400(self, client, admin_headers):
        res = client.get("/reports/deliveries", params={"days": 15}, headers=admin_headers)
        assert res.status_code == 400

    def test_requires_auth(self, client):
        res = client.get("/reports/deliveries")
        assert res.status_code in (401, 403)
