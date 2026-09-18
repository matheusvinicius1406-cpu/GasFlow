"""Testes F8 — Mapa de calor de entregas por bairro.

Cobre o spec §3.8:
- Agregação: contagens por bairro batem com SQL direto (critério do prompt).
- Período: só DELIVERED dentro da janela (7/30/90); entrega fora dela não conta.
- Cache: segunda chamada no TTL retorna cached=True; dados idênticos.
- Tenant: nunca agrega dados de outro tenant.
- Endpoint: GET /reports/heatmap (RBAC de sessão via TestClient).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.application.reports.heatmap import delivery_heatmap, invalidate_heatmap_cache
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


def _delivered(neighborhood: str, days_ago: int, tenant_id: str = "default", lat=None, lng=None) -> DeliveryRecord:
    """Entrega DELIVERED há N dias, com assigned_at 1h antes."""
    delivered_at = datetime.utcnow() - timedelta(days=days_ago)
    return DeliveryRecord(
        delivery_id=f"dlv-{neighborhood}-{days_ago}-{tenant_id}-{datetime.utcnow().timestamp()}",
        tenant_id=tenant_id,
        order_id="O1",
        status="DELIVERED",
        address_neighborhood=neighborhood,
        address_lat=lat,
        address_lng=lng,
        assigned_at=delivered_at - timedelta(hours=1),
        delivered_at=delivered_at,
        timeline=[{"status": "DELIVERED", "timestamp": delivered_at.isoformat()}],
    )


def _sql_counts(db, tenant_id: str, days: int):
    """Contagem direta (critério de aceitação: agregação == SQL direto)."""
    since = datetime.utcnow() - timedelta(days=days)
    rows = db.execute(
        text(
            "SELECT address_neighborhood, COUNT(*) FROM delivery_records "
            "WHERE tenant_id=:t AND status='DELIVERED' AND delivered_at >= :since "
            "GROUP BY address_neighborhood"
        ),
        {"t": tenant_id, "since": since},
    ).fetchall()
    return {(r[0] or "").strip() or "(sem bairro)": r[1] for r in rows}


@pytest.fixture(autouse=True)
def _clean_cache():
    invalidate_heatmap_cache()
    yield
    invalidate_heatmap_cache()


# ═══════════════════════════════════════════════════════════
# Agregação
# ═══════════════════════════════════════════════════════════


class TestAggregation:
    def test_counts_match_direct_sql(self, db):
        for i in range(3):
            db.add(_delivered("Centro", 1 + i, lat=-30.03 + i * 0.01, lng=-51.22 + i * 0.01))
        for i in range(2):
            db.add(_delivered("Moinhos de Vento", 2 + i, lat=-30.00, lng=-51.20))
        db.add(_delivered("Centro", 5))
        db.commit()

        result = delivery_heatmap(db, "default", 30)
        expected = _sql_counts(db, "default", 30)

        got = {n["neighborhood"]: n["count"] for n in result["neighborhoods"]}
        assert got == expected
        assert got["Centro"] == 4
        assert got["Moinhos de Vento"] == 2
        assert result["total"] == 6

    def test_non_delivered_excluded(self, db):
        db.add(_delivered("Centro", 1))
        pending = DeliveryRecord(
            delivery_id="dlv-pending",
            tenant_id="default",
            order_id="O2",
            status="PENDING",
            address_neighborhood="Centro",
        )
        db.add(pending)
        db.commit()

        result = delivery_heatmap(db, "default", 30)
        assert result["total"] == 1  # só a DELIVERED

    def test_outside_period_excluded(self, db):
        db.add(_delivered("Centro", 10))
        db.commit()

        result = delivery_heatmap(db, "default", 7)
        assert result["total"] == 0
        assert result["neighborhoods"] == []

    def test_missing_neighborhood_grouped(self, db):
        db.add(_delivered("", 1))
        db.commit()

        result = delivery_heatmap(db, "default", 30)
        got = {n["neighborhood"]: n["count"] for n in result["neighborhoods"]}
        assert got.get("(sem bairro)") == 1

    def test_centroid_from_bounding_box(self, db):
        db.add(_delivered("Centro", 1, lat=-30.00, lng=-51.20))
        db.add(_delivered("Centro", 2, lat=-30.10, lng=-51.30))
        db.commit()

        result = delivery_heatmap(db, "default", 30)
        center = result["neighborhoods"][0]["center"]
        assert center["lat"] == pytest.approx(-30.05)
        assert center["lng"] == pytest.approx(-51.25)

    def test_sorted_by_count_desc(self, db):
        for i in range(5):
            db.add(_delivered("Grande", 1))
        db.add(_delivered("Pequeno", 1))
        db.commit()

        result = delivery_heatmap(db, "default", 30)
        counts = [n["count"] for n in result["neighborhoods"]]
        assert counts == sorted(counts, reverse=True)
        assert result["neighborhoods"][0]["neighborhood"] == "Grande"


# ═══════════════════════════════════════════════════════════
# Período + cache + tenant
# ═══════════════════════════════════════════════════════════


class TestPeriodAndCache:
    def test_valid_periods(self, db):
        db.add(_delivered("Centro", 10))
        db.commit()
        for days in (7, 30, 90):
            invalidate_heatmap_cache()
            result = delivery_heatmap(db, "default", days)
            assert result["period_days"] == days
        # Fora dos válidos → cai no default 30
        result = delivery_heatmap(db, "default", 42)
        assert result["period_days"] == 30

    def test_cache_hit_within_ttl(self, db):
        db.add(_delivered("Centro", 1))
        db.commit()
        first = delivery_heatmap(db, "default", 30)
        assert first["cached"] is False

        # Novo dado NÃO aparece enquanto o cache vale (TTL 5min)
        db.add(_delivered("Centro", 1))
        db.commit()
        second = delivery_heatmap(db, "default", 30)
        assert second["cached"] is True
        assert second["total"] == first["total"]

    def test_tenant_isolation(self, db):
        db.add(_delivered("Centro", 1, tenant_id="other-tenant"))
        db.commit()

        result = delivery_heatmap(db, "default", 30)
        assert result["total"] == 0  # dados do outro tenant não vazam


# ═══════════════════════════════════════════════════════════
# Endpoint HTTP
# ═══════════════════════════════════════════════════════════


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


class TestHeatmapEndpoint:
    def test_get_heatmap_ok(self, client, admin_headers):
        res = client.get("/reports/heatmap", params={"days": 30}, headers=admin_headers)
        assert res.status_code == 200
        body = res.json()
        assert body["period_days"] == 30
        assert "neighborhoods" in body and "total" in body

    def test_invalid_period_400(self, client, admin_headers):
        res = client.get("/reports/heatmap", params={"days": 42}, headers=admin_headers)
        assert res.status_code == 400

    def test_requires_auth(self, client):
        res = client.get("/reports/heatmap")
        assert res.status_code in (401, 403)
