"""Fase 7.1 — ETA determinístico (domínio, serviço e endpoint).

Cobre:
- velocidade medida vs. default (fallback)
- distância conhecida (0,01° de latitude ≈ 1,11 km)
- amostra escassa / pontos simultâneos não quebram o cálculo
- endpoint: 404 sem entregador, 422 sem coordenadas, 200 com ETA
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.domain.tracking.eta import (
    DEFAULT_SPEED_KMH,
    MIN_ETA_SECONDS,
    average_speed_kmh,
    estimate_eta,
)
from app.infrastructure.database.base import Base
from app.main import app

NOW = datetime(2026, 9, 22, 12, 0, 0)


@pytest.fixture
def app_db():
    """Sessão no MESMO banco que o app usa (o endpoint não vê o :memory:)."""
    from app.infrastructure.database.init_db import engine

    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def set_pragma(c, _):
        cur = c.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


# ── Domínio ─────────────────────────────────────────────


class TestAverageSpeed:
    def test_amostra_escassa_devolve_none(self):
        points = [(-23.55, -46.63, NOW)]
        assert average_speed_kmh(points) is None

    def test_pontos_simultaneos_nao_dividem_por_zero(self):
        same = [(-23.55, -46.63, NOW) for _ in range(4)]
        assert average_speed_kmh(same) is None

    def test_velocidade_medida_de_trajeto_conhecido(self):
        # ~1,11 km em 120s ⇒ ~33,4 km/h (3 pontos = mínimo de amostra)
        points = [
            (-23.55, -46.63, NOW - timedelta(seconds=120)),
            (-23.555, -46.63, NOW - timedelta(seconds=60)),
            (-23.56, -46.63, NOW),
        ]
        speed = average_speed_kmh(points)
        assert speed is not None
        assert 30.0 < speed < 37.0

    def test_parado_devolve_none(self):
        # pontos a poucos metros: velocidade abaixo do ruído de GPS
        points = [
            (-23.55, -46.63, NOW - timedelta(seconds=180)),
            (-23.550001, -46.63, NOW - timedelta(seconds=90)),
            (-23.550002, -46.63, NOW),
        ]
        assert average_speed_kmh(points) is None


class TestEstimateEta:
    def test_usa_velocidade_default_sem_historico(self):
        est = estimate_eta(
            origin=(-23.55, -46.63),
            destination=(-23.56, -46.63),
            now=NOW,
            recent_points=(),
        )
        assert est.speed_source == "default"
        assert est.speed_kmh == round(DEFAULT_SPEED_KMH, 1)
        assert 1.0 < est.distance_km < 1.2
        # ~1,11 km a 28 km/h ⇒ ~143 s
        assert 130 < est.eta_seconds < 160

    def test_usa_velocidade_do_historico_quando_disponivel(self):
        points = [
            (-23.55, -46.63, NOW - timedelta(seconds=120)),
            (-23.555, -46.63, NOW - timedelta(seconds=60)),
            (-23.56, -46.63, NOW),
        ]
        est = estimate_eta(
            origin=(-23.56, -46.63),
            destination=(-23.57, -46.63),
            now=NOW,
            recent_points=points,
        )
        assert est.speed_source == "history"
        assert est.speed_kmh > DEFAULT_SPEED_KMH

    def test_eta_minimo_de_60s(self):
        est = estimate_eta(
            origin=(-23.55, -46.63),
            destination=(-23.55001, -46.63),
            now=NOW,
        )
        assert est.eta_seconds == MIN_ETA_SECONDS

    def test_distancia_conhecida(self):
        est = estimate_eta(
            origin=(0.0, 0.0),
            destination=(0.01, 0.0),
            now=NOW,
        )
        assert 1.0 < est.distance_km < 1.2

    def test_eta_at_e_coerente_com_seconds(self):
        est = estimate_eta(origin=(0.0, 0.0), destination=(0.01, 0.0), now=NOW)
        assert (est.eta_at - NOW).total_seconds() == est.eta_seconds


# ── Serviço + endpoint ──────────────────────────────────


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


class TestEtaEndpoint:
    def _make_delivery(self, db, *, driver_id, lat, lng, status="EN_ROUTE"):
        from app.infrastructure.repositories.delivery_persistence_model import DeliveryRecord

        delivery_id = f"dlv-eta-{uuid.uuid4().hex[:10]}"
        db.add(
            DeliveryRecord(
                delivery_id=delivery_id,
                tenant_id="default",
                order_id=f"ord-{uuid.uuid4().hex[:8]}",
                status=status,
                version=1,
                driver_id=driver_id,
                address_lat=lat,
                address_lng=lng,
            )
        )
        db.commit()
        return delivery_id

    def _put_location(self, db, driver_id, lat, lng):
        from app.infrastructure.repositories.delivery_persistence_repository import (
            SQLAlchemyDriverLocationRepository,
        )

        SQLAlchemyDriverLocationRepository(db).upsert_location("default", driver_id, lat, lng)

    def test_sem_coordenadas_no_endereco_devolve_422(self, app_db, client, admin_headers):
        delivery_id = self._make_delivery(app_db, driver_id="drv-eta-1", lat=None, lng=None)
        res = client.get(f"/delivery/deliveries/{delivery_id}/eta", headers=admin_headers)
        assert res.status_code == 422, res.text

    def test_sem_entregador_devolve_404(self, app_db, client, admin_headers):
        delivery_id = self._make_delivery(app_db, driver_id=None, lat=-23.55, lng=-46.63)
        res = client.get(f"/delivery/deliveries/{delivery_id}/eta", headers=admin_headers)
        assert res.status_code == 404, res.text

    def test_sem_posicao_do_entregador_devolve_404(self, app_db, client, admin_headers):
        delivery_id = self._make_delivery(app_db, driver_id="drv-eta-sempos", lat=-23.55, lng=-46.63)
        res = client.get(f"/delivery/deliveries/{delivery_id}/eta", headers=admin_headers)
        assert res.status_code == 404, res.text

    def test_entrega_inexistente_devolve_404(self, client, admin_headers):
        res = client.get("/delivery/deliveries/nao-existe/eta", headers=admin_headers)
        assert res.status_code == 404, res.text

    def test_devolve_eta_com_distancia_e_origem(self, app_db, client, admin_headers):
        driver_id = f"drv-eta-{uuid.uuid4().hex[:6]}"
        delivery_id = self._make_delivery(app_db, driver_id=driver_id, lat=-23.56, lng=-46.63)
        self._put_location(app_db, driver_id, -23.55, -46.63)

        res = client.get(f"/delivery/deliveries/{delivery_id}/eta", headers=admin_headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["driver_id"] == driver_id
        assert body["speed_source"] == "default"
        assert 1.0 < body["distance_km"] < 1.2
        assert body["eta_seconds"] > 0
        assert body["origin"]["latitude"] == -23.55
        assert body["destination"]["latitude"] == -23.56
