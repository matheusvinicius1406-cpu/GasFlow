"""Fase 7.3 — alertas de entregador parado/desviado.

Cobre:
- parado: deslocamento abaixo do raio → STALLED; acima → sem alerta
- parado sem entrega em rota não alerta (descanso, não incidente)
- desvio: acima do limiar → DEVIATED; abaixo → sem alerta
- endereço sem coordenadas nunca afirma desvio
- publicação do evento `driver.alert` no barramento (uma vez por avaliação)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.application.tracking.alerts_service import (
    DEVIATION_KM,
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


def _history(db, driver_id, points):
    SQLAlchemyDriverLocationRepository(db).bulk_insert_history("default", driver_id, points)


def _point(lat, lng, seconds_ago):
    return {
        "latitude": lat,
        "longitude": lng,
        "recorded_at": (NOW - timedelta(seconds=seconds_ago)).isoformat(),
    }


def _last_location(db, driver_id, lat, lng):
    SQLAlchemyDriverLocationRepository(db).upsert_location("default", driver_id, lat, lng)


class TestStalled:
    def test_parado_com_entrega_em_rota_alerta(self, db):
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        delivery_id = _add_delivery(db, driver_id=driver_id, lat=-23.70, lng=-46.63)
        # ~5 m de deslocamento em 8 min
        _history(
            db,
            driver_id,
            [
                _point(-23.55, -46.63, 480),
                _point(-23.55002, -46.63, 240),
                _point(-23.55004, -46.63, 60),
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
                _point(-23.55, -46.63, 480),
                _point(-23.60, -46.63, 240),
                _point(-23.65, -46.63, 60),
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
                _point(-23.55, -46.63, 480),
                _point(-23.55002, -46.63, 60),
            ],
        )

        alerts = TrackingAlertsService(db, "default").evaluate(driver_id=driver_id, now=NOW)
        assert [a.kind for a in alerts] == []


class TestDeviated:
    def test_desviado_acima_do_limiar(self, db):
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        # endereço a ~11 km da posição atual
        delivery_id = _add_delivery(db, driver_id=driver_id, lat=-23.65, lng=-46.63)
        _last_location(db, driver_id, -23.55, -46.63)

        alerts = TrackingAlertsService(db, "default").evaluate(driver_id=driver_id, delivery_id=delivery_id, now=NOW)

        deviated = [a for a in alerts if a.kind == "DEVIATED"]
        assert len(deviated) == 1
        assert deviated[0].detail["deviation_km"] > DEVIATION_KM

    def test_perto_do_endereco_nao_desvia(self, db):
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        delivery_id = _add_delivery(db, driver_id=driver_id, lat=-23.5505, lng=-46.63)
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
    def test_publica_driver_alert_no_barramento(self, db):
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        delivery_id = _add_delivery(db, driver_id=driver_id, lat=-23.65, lng=-46.63)
        _last_location(db, driver_id, -23.55, -46.63)

        captured: list[DomainEvent] = []
        bus = get_event_bus()
        bus.subscribe(EventType.DRIVER_ALERT, captured.append)
        try:
            TrackingAlertsService(db, "default").evaluate(driver_id=driver_id, delivery_id=delivery_id, now=NOW)
        finally:
            bus.unsubscribe(EventType.DRIVER_ALERT, captured.append)

        assert len(captured) == 1
        event = captured[0]
        assert event.type == EventType.DRIVER_ALERT
        assert event.aggregate_id == driver_id
        assert event.data["kind"] == "DEVIATED"
        assert event.data["delivery_id"] == delivery_id

    def test_sem_alerta_nao_publica(self, db):
        driver_id = f"drv-{uuid.uuid4().hex[:6]}"
        delivery_id = _add_delivery(db, driver_id=driver_id, lat=-23.5505, lng=-46.63)
        _last_location(db, driver_id, -23.55, -46.63)

        captured: list[DomainEvent] = []
        bus = get_event_bus()
        bus.subscribe(EventType.DRIVER_ALERT, captured.append)
        try:
            TrackingAlertsService(db, "default").evaluate(driver_id=driver_id, delivery_id=delivery_id, now=NOW)
        finally:
            bus.unsubscribe(EventType.DRIVER_ALERT, captured.append)

        assert captured == []
