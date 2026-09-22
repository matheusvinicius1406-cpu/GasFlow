"""Fase 4 — ingestão de posições pelo entregador + realtime + histórico.

Cobre:
- `POST /driver/locations` exige `require_driver` (admin/operador → 403)
- lote de 500 aceito; acima de 500 rejeitado
- publicação no barramento existente (evento `driver.location_updated`)
- roteamento do evento para `tenant:{id}` (o canal que o painel assina)
- `GET /driver/locations/history` restrito a admin/operador e escopado por tenant
- `today_distance_km` real no `/driver/me`
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.domain.events.event_bus import DomainEvent, EventType, get_event_bus
from app.infrastructure.realtime.websocket import ConnectionManager
from app.main import app


class FakeWS:
    def __init__(self, conn_id: int = 0):
        self.conn_id = conn_id
        self.accepted = False
        self.sent: list[str] = []

    async def accept(self):
        self.accepted = True

    async def send_text(self, message: str):
        self.sent.append(message)

    def __hash__(self):
        return hash(("fakews", self.conn_id))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        # Janela LGPD ampla para o teste não depender do relógio da máquina.
        from sqlalchemy.orm import Session as DBSession

        from app.application.settings.settings_service import SettingsService
        from app.infrastructure.database.init_db import engine

        db = DBSession(bind=engine)
        try:
            svc = SettingsService(db)
            svc.update("driver.work_hours.start", "00:00")
            svc.update("driver.work_hours.end", "23:59")
        finally:
            db.close()
        yield c


@pytest.fixture(scope="module")
def admin_headers(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _active_driver(client, admin_headers):
    """Cria entregador, troca a senha e devolve (driver_id, headers)."""
    res = client.post(
        "/admin/drivers",
        headers=admin_headers,
        json={
            "name": "Entregador Tracking",
            "phone": "91999991111",
            "document": "000.000.000-00",
            "username": f"trk_{uuid.uuid4().hex[:8]}",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    login = client.post("/auth/login", json={"username": body["username"], "password": body["temporary_password"]})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    changed = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": body["temporary_password"], "new_password": "NovaSenha123"},
    )
    assert changed.status_code == 200, changed.text
    return body["driver_id"], headers


def _points(n: int, base: datetime | None = None):
    base = base or datetime.utcnow()
    return [
        {
            "latitude": -23.55 - i * 0.0001,
            "longitude": -46.63,
            "recorded_at": (base - timedelta(seconds=(n - i) * 20)).isoformat(),
        }
        for i in range(n)
    ]


# ── Autorização ─────────────────────────────────────────


def test_ingest_requires_driver(client, admin_headers):
    res = client.post("/driver/locations", headers=admin_headers, json={"points": _points(2)})
    assert res.status_code == 403, res.text


def test_history_requires_operator_or_admin(client, admin_headers):
    driver_id, driver_headers = _active_driver(client, admin_headers)
    res = client.get(f"/driver/locations/history?driver_id={driver_id}", headers=driver_headers)
    assert res.status_code == 403, res.text


# ── Ingestão ────────────────────────────────────────────


def test_ingest_accepts_batch(client, admin_headers):
    _, driver_headers = _active_driver(client, admin_headers)
    res = client.post("/driver/locations", headers=driver_headers, json={"points": _points(5)})
    assert res.status_code == 200, res.text
    assert res.json()["accepted"] == 5


def test_ingest_500_accepted_and_501_rejected(client, admin_headers):
    _, driver_headers = _active_driver(client, admin_headers)

    ok = client.post("/driver/locations", headers=driver_headers, json={"points": _points(500)})
    assert ok.status_code == 200, ok.text
    assert ok.json()["accepted"] == 500

    too_big = client.post("/driver/locations", headers=driver_headers, json={"points": _points(501)})
    assert too_big.status_code == 400, too_big.text


def test_ingest_publishes_driver_location_event(client, admin_headers):
    """O endpoint publica no barramento existente (rota p/ tenant/operations depois)."""
    _, driver_headers = _active_driver(client, admin_headers)
    captured: list[DomainEvent] = []
    bus = get_event_bus()
    bus.subscribe(EventType.DRIVER_LOCATION_UPDATED, captured.append)
    try:
        res = client.post("/driver/locations", headers=driver_headers, json={"points": _points(3)})
        assert res.status_code == 200, res.text
    finally:
        bus.unsubscribe(EventType.DRIVER_LOCATION_UPDATED, captured.append)

    assert captured, "nenhum evento driver.location_updated publicado"
    event = captured[-1]
    assert event.data["latitude"] is not None
    assert event.data["longitude"] is not None
    assert event.data["driver_id"]


def test_ingest_out_of_hours_is_rejected(client, admin_headers):
    _, driver_headers = _active_driver(client, admin_headers)

    from sqlalchemy.orm import Session as DBSession

    from app.application.settings.settings_service import SettingsService
    from app.infrastructure.database.init_db import engine

    db = DBSession(bind=engine)
    try:
        svc = SettingsService(db)
        svc.update("driver.work_hours.start", "23:00")
        svc.update("driver.work_hours.end", "23:00")  # janela vazia
        try:
            res = client.post("/driver/locations", headers=driver_headers, json={"points": _points(2)})
            assert res.status_code == 403, res.text
        finally:
            svc.update("driver.work_hours.start", "00:00")
            svc.update("driver.work_hours.end", "23:59")
    finally:
        db.close()


# ── Realtime: roteamento do evento ──────────────────────


@pytest.mark.asyncio
async def test_driver_location_routes_to_tenant_channel():
    """`driver.location_updated` chega em `tenant:{id}` (canal do painel)."""
    manager = ConnectionManager()
    ws_admin = FakeWS(1)
    ws_other = FakeWS(2)
    await manager.connect(ws_admin, "tenant:t1", {})
    await manager.connect(ws_other, "tenant:t2", {})

    event = DomainEvent(
        type=EventType.DRIVER_LOCATION_UPDATED,
        tenant_id="t1",
        aggregate_id="d1",
        actor_type="DRIVER",
        data={"driver_id": "d1", "latitude": -23.55, "longitude": -46.63},
    )
    await manager.broadcast_event(event)

    assert len(ws_admin.sent) == 1
    payload = json.loads(ws_admin.sent[0])
    assert payload["event"]["data"]["latitude"] == -23.55
    assert ws_other.sent == [], "evento vazou para outro tenant"


# ── Histórico ───────────────────────────────────────────


def test_history_returns_points_scoped_by_tenant(client, admin_headers):
    driver_id, driver_headers = _active_driver(client, admin_headers)
    client.post("/driver/locations", headers=driver_headers, json={"points": _points(4)})

    res = client.get(f"/driver/locations/history?driver_id={driver_id}", headers=admin_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["count"] == 4
    assert body["points"][0]["latitude"] is not None

    # Outro tenant não enxerga nada (mesmo driver_id).
    from app.infrastructure.database.init_db import engine
    from sqlalchemy.orm import Session as DBSession

    from app.infrastructure.repositories.delivery_persistence_repository import (
        SQLAlchemyDriverLocationRepository,
    )

    db = DBSession(bind=engine)
    try:
        repo = SQLAlchemyDriverLocationRepository(db)
        assert repo.get_history("outro-tenant", driver_id) == []
    finally:
        db.close()


# ── Distância do dia (Fase 3.3 no app) ──────────────────


def test_today_distance_visible_in_driver_me(client, admin_headers):
    driver_id, driver_headers = _active_driver(client, admin_headers)
    base = datetime.utcnow()
    points = [
        {"latitude": -23.55, "longitude": -46.63, "recorded_at": (base - timedelta(minutes=2)).isoformat()},
        {"latitude": -23.56, "longitude": -46.63, "recorded_at": (base - timedelta(minutes=1)).isoformat()},
    ]
    ingest = client.post("/driver/locations", headers=driver_headers, json={"points": points})
    assert ingest.status_code == 200, ingest.text

    me = client.get("/driver/me", headers=driver_headers)
    assert me.status_code == 200, me.text
    assert me.json()["driver_id"] == driver_id
    assert me.json()["today_distance_km"] > 1.0
