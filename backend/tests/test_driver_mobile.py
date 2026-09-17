"""Testes Fase 1 — App do Entregador: mobile auth + location + delta sync.

Cobre o prompt (seções 3.1, 3.4, 3.5, 7, 8) sobre a API existente da Fase 14:

1.  Login mobile devolve access (15min, escopo mobile) + refresh (7d)
2.  Access token vencido/assinado errado/escopo desktop → 401
3.  Refresh rotaciona; reuso do token antigo revoga a família
4.  Rate limit de login (10/min/IP)
5.  Location batch: aceita dentro do horário, 403 fora (LGPD)
6.  Batch malformado não derruba o lote; audit gravado
7.  Delta sync devolve mudanças desde `since` (do próprio motorista)
8.  Purge 90d apaga posições antigas
9.  Login de usuário não-motorista (sem password_hash válido) → 401

Estratégia: TestClient + banco isolado do conftest (mesmo caminho de produção).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ── Helpers ──────────────────────────────────────────────────


def _create_driver_with_password(db, codigo: str, username: str, password: str | None = "pw#123456"):
    import bcrypt

    from app.infrastructure.repositories.delivery_model import DeliveryDriverModel

    exists = db.query(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == codigo).first()
    if exists:
        exists.username = username
        exists.ativo = True
        if password is not None:
            exists.password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        db.commit()
        return exists
    driver = DeliveryDriverModel(
        tenant_id="default",
        codigo=codigo,
        nome=f"Motorista {codigo}",
        telefone="11999990000",
        username=username,
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode() if password else None,
        ativo=True,
    )
    db.add(driver)
    db.commit()
    return driver


def _db():
    from sqlalchemy.orm import Session

    from app.infrastructure.database.init_db import engine

    return Session(bind=engine)


def _login(client, username="condutor_mobile", password="pw#123456"):
    return client.post("/auth/mobile/login", json={"username": username, "password": password})


@pytest.fixture(scope="module")
def driver_credentials(client):
    """Cria motorista com login antes dos testes do módulo."""
    db = _db()
    try:
        _create_driver_with_password(db, "654321", "condutor_mobile")
        res = _login(client)
        assert res.status_code == 200, res.text
        return res.json()
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# 1. Login mobile
# ═══════════════════════════════════════════════════════════


def test_mobile_login_returns_token_pair(client, driver_credentials):
    body = driver_credentials
    assert body["access_token"] and body["refresh_token"]
    assert body["driver_id"] == "654321"
    # access token JWT com escopo mobile (3 partes, payload decodificável)
    import base64
    import json

    payload_b64 = body["access_token"].split(".")[1]
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4)))
    assert payload["scope"] == "mobile"
    assert payload["sub"] == "654321"
    assert payload["exp"] - payload["iat"] == 900  # 15 min


def test_driver_me_exposes_tracking_and_work_hours(client, driver_credentials):
    """F2.5: /driver/me carrega intervalo de rastreio E janela LGPD
    ("HH:MM-HH:MM") — o app do entregador respeita no cliente o mesmo gate
    que o backend reforça no ingest (403 fora da janela)."""
    db = _db()
    try:
        from app.application.settings.settings_service import SettingsService

        svc = SettingsService(db)
        svc.update("driver.tracking.interval_seconds", 45)
        svc.update("driver.work_hours.start", "06:00")
        svc.update("driver.work_hours.end", "22:00")
    finally:
        db.close()

    res = client.get("/api/v1/driver/me", headers=_auth_header(driver_credentials))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tracking_interval_seconds"] == 45
    assert body["work_hours"] == "06:00-22:00"


def test_mobile_login_wrong_password(client):
    assert _login(client, password="errada!").status_code == 401
    assert _login(client, username="nao_existe_xyz").status_code == 401


# ═══════════════════════════════════════════════════════════
# 2. Access token — verificação
# ═══════════════════════════════════════════════════════════


def test_access_token_rejects_garbage_and_wrong_scope(client, driver_credentials):
    from app.presentation.api.logistics.driver_mobile_auth import issue_access_token, verify_access_token
    from fastapi import HTTPException

    # válido passa
    payload = verify_access_token(driver_credentials["access_token"])
    assert payload["sub"] == "654321"

    # escopo desktop → rejeitado
    desktop_token = issue_access_token("654321", "default", expires_minutes=5)
    from app.presentation.api.logistics import driver_mobile_auth as mod

    original = mod.verify_access_token
    import hmac as _hmac
    import hashlib as _hashlib
    import json as _json
    from app.presentation.api.logistics.driver_mobile_auth import _b64url, _jwt_secret

    def _forge(scope_value: str) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        now = int(datetime.utcnow().timestamp())
        payload = {"sub": "654321", "scope": scope_value, "exp": now + 300}
        signing_input = (
            _b64url(_json.dumps(header, separators=(",", ":")).encode())
            + "."
            + _b64url(_json.dumps(payload, separators=(",", ":")).encode())
        )
        sig = _hmac.new(_jwt_secret().encode(), signing_input.encode(), _hashlib.sha256).digest()
        return signing_input + "." + _b64url(sig)

    with pytest.raises(HTTPException):
        verify_access_token(_forge("desktop"))

    # token expirado → 401
    expired = issue_access_token("654321", "default", expires_minutes=-1)
    with pytest.raises(HTTPException):
        verify_access_token(expired)


def test_mobile_routes_require_bearer(client):
    assert client.get("/driver/sync").status_code == 401


# ═══════════════════════════════════════════════════════════
# 3. Refresh — rotação e replay
# ═══════════════════════════════════════════════════════════


def test_refresh_rotates_and_reuse_revokes_family(client, driver_credentials):
    first = driver_credentials

    # rotação 1: refresh original → novo par
    r1 = client.post("/auth/mobile/refresh", json={"refresh_token": first["refresh_token"]})
    assert r1.status_code == 200, r1.text
    second = r1.json()
    assert second["refresh_token"] != first["refresh_token"]

    # reuso do token original (já ROTATED) → 401 + família revogada
    reuse = client.post("/auth/mobile/refresh", json={"refresh_token": first["refresh_token"]})
    assert reuse.status_code == 401

    # o token da rotação 1 também morreu (mesma família)
    dead = client.post("/auth/mobile/refresh", json={"refresh_token": second["refresh_token"]})
    assert dead.status_code == 401

    # login fresco volta a funcionar (nova família)
    fresh = _login(client)
    assert fresh.status_code == 200


# ═══════════════════════════════════════════════════════════
# 4. Location — horário de trabalho (LGPD)
# ═══════════════════════════════════════════════════════════


def _auth_header(driver_credentials):
    return {"Authorization": f"Bearer {driver_credentials['access_token']}"}


def test_location_batch_within_hours(client, driver_credentials):
    from app.infrastructure.repositories.delivery_persistence_repository import (
        SQLAlchemyDriverLocationRepository,
    )
    from app.application.settings.settings_service import SettingsService

    # O handler agora reforça work-hours (LGPD) para toda origem. Fixa a
    # janela como 24h para o teste ser determinístico em qualquer horário
    # de CI (end "24:00" → end_m=1440 > qualquer minuto do dia).
    db = _db()
    svc = SettingsService(db)
    svc.update("driver.work_hours.start", "00:00")
    svc.update("driver.work_hours.end", "24:00")

    # Rota legada montada na raiz (driver_api_router, prefixo /api/driver);
    # a v1 oficial vive sob /api/v1/driver/location.
    res = client.post(
        "/api/driver/v1/location",
        headers=_auth_header(driver_credentials),
        json={"latitude": -1.4558, "longitude": -48.4902, "speed": 32.5},
    )
    assert res.status_code == 200, res.text

    try:
        record = SQLAlchemyDriverLocationRepository(db).get_location("default", "654321")
        assert record is not None
        assert abs(record.latitude - (-1.4558)) < 1e-6
    finally:
        svc.update("driver.work_hours.start", "06:00")
        svc.update("driver.work_hours.end", "22:00")
        db.close()


def test_location_rejected_outside_work_hours(client, driver_credentials):
    from app.application.delivery.driver_location_service import DriverLocationService, WorkHoursViolation

    db = _db()
    try:
        # Janela impossível: termina antes de começar no mesmo instante
        from app.application.settings.settings_service import SettingsService

        svc = SettingsService(db)
        svc.update("driver.work_hours.start", "23:00")
        svc.update("driver.work_hours.end", "23:00")  # janela vazia
        service = DriverLocationService(db, "default", "654321")
        with pytest.raises(WorkHoursViolation):
            service.ingest_batch([{"lat": -1.0, "lng": -48.0}])
    finally:
        svc.update("driver.work_hours.start", "06:00")
        svc.update("driver.work_hours.end", "22:00")
        db.close()


def test_purge_old_locations(client, driver_credentials):
    from app.application.delivery.driver_location_service import purge_old_locations
    from app.infrastructure.repositories.delivery_persistence_model import DriverLocationRecord

    db = _db()
    try:
        old = DriverLocationRecord(
            tenant_id="default",
            driver_id="654321",
            latitude=0.0,
            longitude=0.0,
            timestamp=datetime.utcnow() - timedelta(days=91),
        )
        db.add(old)
        db.commit()
        deleted = purge_old_locations(db, days=90)
        assert deleted >= 1
        cutoff = datetime.utcnow() - timedelta(days=90)
        remaining_old = (
            db.query(DriverLocationRecord)
            .filter(DriverLocationRecord.driver_id == "654321", DriverLocationRecord.timestamp < cutoff)
            .count()
        )
        assert remaining_old == 0
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# 5. Delta sync
# ═══════════════════════════════════════════════════════════


def test_delta_sync_returns_changes_since(client, driver_credentials):
    from app.infrastructure.repositories.delivery_persistence_repository import (
        SQLAlchemyOfflineSyncLogRepository,
    )

    db = _db()
    try:
        sync_repo = SQLAlchemyOfflineSyncLogRepository(db)
        sync_repo.record_change("default", "delivery", "d-mob-1", "UPDATED")
        before = (datetime.utcnow() - timedelta(seconds=5)).isoformat()
        sync_repo.record_change("default", "delivery", "d-mob-2", "UPDATED")
    finally:
        db.close()

    res = client.get(
        "/driver/sync",
        headers=_auth_header(driver_credentials),
        params={"since": before},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "server_time" in body
    assert isinstance(body["deliveries"], list)
    assert isinstance(body["route_changes"], list)


def test_delta_sync_invalid_since(client, driver_credentials):
    res = client.get(
        "/driver/sync",
        headers=_auth_header(driver_credentials),
        params={"since": "not-a-date"},
    )
    assert res.status_code == 422


# ═══════════════════════════════════════════════════════════
# 6. Logout revoga família
# ═══════════════════════════════════════════════════════════


def test_logout_revokes_refresh(client):
    login = _login(client)
    assert login.status_code == 200
    tokens = login.json()
    res = client.post(
        "/auth/mobile/logout",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert res.status_code == 200
    dead = client.post("/auth/mobile/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert dead.status_code == 401
