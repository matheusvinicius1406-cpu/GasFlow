"""Parte 1 (fixes 1 e 2) — alertas de entregador parado/desviado.

Cobre os bugs corrigidos:
- **cooldown**: não realerta dentro de 15 min; realerta depois;
- **reset por movimento**: parou → andou → parou de novo é evento novo;
- **gate do DEVIATED**: só em `EN_ROUTE` e só perto do destino (< 3 km),
  evitando o falso positivo da volta ao depósito;
- parado sem entrega ativa não alerta;
- publicação única no barramento por avaliação que dispara.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.application.tracking.alerts_service import (
    ALERT_COOLDOWN_MINUTES,
    DEVIATION_KM,
    DEVIATION_PROXIMITY_KM,
    STALLED_MINUTES,
    TrackingAlertsService,
)
from app.domain.events.event_bus import DomainEvent, EventType, get_event_bus
from app.infrastructure.database.base import Base
from app.infrastructure.repositories.delivery_persistence_model import DeliveryRecord
from app.infrastructure.repositories.delivery_persistence_repository import (
    SQLAlchemyDriverLocationRepository,
)

NOW = datetime(2026, 9, 22, 12, 0, 0)


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


def _add_delivery(db, *, driver_id, lat=-23.56, lng=-46.63, status="EN_ROUTE"):
    delivery_id = f"dlv-alt-{uuid.uuid4().hex[:10]}"
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


def _point(lat, lng, when):
    return {"latitude": lat, "longitude": lng, "recorded_at": when.isoformat()}


def _history(db, driver_id, points):
    SQLAlchemyDriverLocationRepository(db).bulk_insert_history("default", driver_id, points)


def _last_location(db, driver_id, lat, lng):
    SQLAlchemyDriverLocationRepository(db).upsert_location("default", driver_id, lat, lng)


def _capture_alerts():
    """Assina o barramento e devolve (lista, cleanup)."""
    captured: list[DomainEvent] = []
    bus = get_event_bus()
    bus.subscribe(EventType.DRIVER_ALERT, captured.append)
    return captured, lambda: bus.unsubscribe(EventType.DRIVER_ALERT, captured.append)


class TestStalled:
    def test_parado_com_entrega_em_rota_alerta(self, db):
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        delivery_id = _add_delivery(db, driver_id=driver_id, lat=-23.70, lng=-46.63)
        _history(
            db,
            driver_id,
            [
                _point(-23.55, -46.63, NOW - timedelta(minutes=8)),
                _point(-23.55002, -46.63, NOW - timedelta(minutes=4)),
                _point(-23.55004, -46.63, NOW - timedelta(minutes=1)),
            ],
        )

        alerts = TrackingAlertsService(db, "default").evaluate(driver_id=driver_id, now=NOW)

        stalled = [a for a in alerts if a.kind == "STALLED"]
        assert len(stalled) == 1
        assert stalled[0].delivery_id == delivery_id
        assert stalled[0].detail["minutes"] == STALLED_MINUTES

    def test_em_movimento_nao_alerta(self, db):
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        _add_delivery(db, driver_id=driver_id, lat=-23.90, lng=-46.63)
        _history(
            db,
            driver_id,
            [
                _point(-23.55, -46.63, NOW - timedelta(minutes=8)),
                _point(-23.60, -46.63, NOW - timedelta(minutes=4)),
                _point(-23.65, -46.63, NOW - timedelta(minutes=1)),
            ],
        )

        alerts = TrackingAlertsService(db, "default").evaluate(driver_id=driver_id, now=NOW)
        assert [a.kind for a in alerts] == []

    def test_sem_entrega_em_rota_nao_alerta(self, db):
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        _history(
            db,
            driver_id,
            [
                _point(-23.55, -46.63, NOW - timedelta(minutes=8)),
                _point(-23.55002, -46.63, NOW - timedelta(minutes=1)),
            ],
        )

        alerts = TrackingAlertsService(db, "default").evaluate(driver_id=driver_id, now=NOW)
        assert [a.kind for a in alerts] == []


class TestCooldown:
    def _stalled_driver(self, db):
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        _add_delivery(db, driver_id=driver_id, lat=-23.70, lng=-46.63)
        _history(
            db,
            driver_id,
            [
                _point(-23.55, -46.63, NOW - timedelta(minutes=8)),
                _point(-23.55002, -46.63, NOW - timedelta(minutes=1)),
            ],
        )
        return driver_id

    def test_nao_realerta_dentro_do_cooldown(self, db):
        driver_id = self._stalled_driver(db)
        service = TrackingAlertsService(db, "default")

        first = service.evaluate(driver_id=driver_id, now=NOW)
        second = service.evaluate(driver_id=driver_id, now=NOW + timedelta(minutes=5))

        assert [a.kind for a in first] == ["STALLED"]
        assert second == [], "alerta republicado dentro do cooldown"

    def test_realerta_depois_do_cooldown(self, db):
        driver_id = self._stalled_driver(db)
        service = TrackingAlertsService(db, "default")

        service.evaluate(driver_id=driver_id, now=NOW)

        # Continua parado, com pontos frescos dentro da nova janela.
        later = NOW + timedelta(minutes=ALERT_COOLDOWN_MINUTES + 1)
        _history(
            db,
            driver_id,
            [
                _point(-23.55, -46.63, later - timedelta(minutes=6)),
                _point(-23.55002, -46.63, later - timedelta(minutes=1)),
            ],
        )
        after = service.evaluate(driver_id=driver_id, now=later)

        assert [a.kind for a in after] == ["STALLED"]

    def test_volta_a_se_mover_zera_o_cooldown(self, db):
        """Parou → andou → parou de novo: é um evento novo, tem que alertar."""
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        _add_delivery(db, driver_id=driver_id, lat=-23.90, lng=-46.63)
        _history(
            db,
            driver_id,
            [
                _point(-23.55, -46.63, NOW - timedelta(minutes=8)),
                _point(-23.55002, -46.63, NOW - timedelta(minutes=1)),
            ],
        )
        service = TrackingAlertsService(db, "default")

        # 1) parado → alerta
        assert [a.kind for a in service.evaluate(driver_id=driver_id, now=NOW)] == ["STALLED"]

        # 2) voltou a andar (> 200 m) → sem alerta e cooldown zerado
        move_at = NOW + timedelta(minutes=5)
        _history(
            db,
            driver_id,
            [
                _point(-23.55, -46.63, NOW + timedelta(minutes=2)),
                _point(-23.56, -46.63, move_at),
            ],
        )
        assert service.evaluate(driver_id=driver_id, now=move_at) == []

        # 3) parou de novo, já fora da janela dos pontos de movimento
        stop_at = NOW + timedelta(minutes=20)
        _history(
            db,
            driver_id,
            [
                _point(-23.56, -46.63, NOW + timedelta(minutes=16)),
                _point(-23.56002, -46.63, NOW + timedelta(minutes=19)),
            ],
        )
        assert [a.kind for a in service.evaluate(driver_id=driver_id, now=stop_at)] == ["STALLED"]


class TestDeviated:
    def test_desviado_perto_do_destino_alerta(self, db):
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        # ~2,0 km do endereço — acima do limiar (1,2) e dentro da proximidade (3)
        delivery_id = _add_delivery(db, driver_id=driver_id, lat=-23.568, lng=-46.63)
        _last_location(db, driver_id, -23.55, -46.63)

        alerts = TrackingAlertsService(db, "default").evaluate(driver_id=driver_id, delivery_id=delivery_id, now=NOW)

        deviated = [a for a in alerts if a.kind == "DEVIATED"]
        assert len(deviated) == 1
        assert DEVIATION_KM < deviated[0].detail["deviation_km"] <= DEVIATION_PROXIMITY_KM

    def test_perto_do_endereco_nao_desvia(self, db):
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        # ~0,55 km — dentro do limiar
        delivery_id = _add_delivery(db, driver_id=driver_id, lat=-23.555, lng=-46.63)
        _last_location(db, driver_id, -23.55, -46.63)

        alerts = TrackingAlertsService(db, "default").evaluate(driver_id=driver_id, delivery_id=delivery_id, now=NOW)
        assert [a.kind for a in alerts] == []

    def test_longe_do_destino_nao_acusa_desvio(self, db):
        """Volta do depósito: 5+ km do endereço não é desvio, é o trajeto."""
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        delivery_id = _add_delivery(db, driver_id=driver_id, lat=-23.60, lng=-46.63)
        _last_location(db, driver_id, -23.55, -46.63)

        alerts = TrackingAlertsService(db, "default").evaluate(driver_id=driver_id, delivery_id=delivery_id, now=NOW)
        assert [a.kind for a in alerts] == []

    @pytest.mark.parametrize("status", ["ASSIGNED", "DISPATCHED"])
    def test_fora_de_en_route_nao_acusa_desvio(self, db, status):
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        delivery_id = _add_delivery(db, driver_id=driver_id, lat=-23.568, lng=-46.63, status=status)
        _last_location(db, driver_id, -23.55, -46.63)

        alerts = TrackingAlertsService(db, "default").evaluate(driver_id=driver_id, delivery_id=delivery_id, now=NOW)
        assert [a.kind for a in alerts] == []

    def test_endereco_sem_coordenadas_nao_afirma_desvio(self, db):
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        delivery_id = _add_delivery(db, driver_id=driver_id, lat=None, lng=None)
        _last_location(db, driver_id, -23.55, -46.63)

        alerts = TrackingAlertsService(db, "default").evaluate(driver_id=driver_id, delivery_id=delivery_id, now=NOW)
        assert [a.kind for a in alerts] == []


class TestPublishing:
    def test_publica_driver_alert_uma_vez(self, db):
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        delivery_id = _add_delivery(db, driver_id=driver_id, lat=-23.568, lng=-46.63)
        _last_location(db, driver_id, -23.55, -46.63)

        captured, cleanup = _capture_alerts()
        try:
            service = TrackingAlertsService(db, "default")
            service.evaluate(driver_id=driver_id, delivery_id=delivery_id, now=NOW)
            # segunda avaliação dentro do cooldown não republica
            service.evaluate(driver_id=driver_id, delivery_id=delivery_id, now=NOW + timedelta(minutes=1))
        finally:
            cleanup()

        assert len(captured) == 1
        event = captured[0]
        assert event.type == EventType.DRIVER_ALERT
        assert event.aggregate_id == driver_id
        assert event.data["kind"] == "DEVIATED"
        assert event.data["delivery_id"] == delivery_id
        assert event.tenant_id == "default"

    def test_sem_alerta_nao_publica(self, db):
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        delivery_id = _add_delivery(db, driver_id=driver_id, lat=-23.5545, lng=-46.63)
        _last_location(db, driver_id, -23.55, -46.63)

        captured, cleanup = _capture_alerts()
        try:
            TrackingAlertsService(db, "default").evaluate(driver_id=driver_id, delivery_id=delivery_id, now=NOW)
        finally:
            cleanup()

        assert captured == []
