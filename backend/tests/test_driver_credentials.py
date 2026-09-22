"""Cadastro de entregador com credencial + gate de troca de senha (Fase 1).

Cobre o fluxo novo: o admin cadastra o entregador, o sistema gera a credencial
com senha temporária, o entregador autentica pela auth PRINCIPAL (`/auth/login`)
e é forçado a trocar a senha antes de acessar `/driver/*` ou o WebSocket.

O entregador já existia como entidade de negócio (`delivery_drivers`); aqui a
novidade é a credencial vinculada (`auth_users.driver_id`) e o namespace
`/driver/*` protegido por `require_driver`.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200, res.text
    return res.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ── Helpers ─────────────────────────────────────────────


def _create_driver(client, admin_headers, *, name="Entregador Teste", phone="91999990000"):
    """Cadastra entregador e devolve (driver_id, username, temporary_password)."""
    res = client.post(
        "/admin/drivers",
        headers=admin_headers,
        json={
            "name": name,
            "phone": phone,
            "document": "000.000.000-00",
            "username": f"drv_{uuid.uuid4().hex[:8]}",  # evita colisão entre execuções
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    return body["driver_id"], body["username"], body["temporary_password"]


def _login(client, username, password):
    return client.post("/auth/login", json={"username": username, "password": password})


def _insert_delivery(driver_codigo: str, tenant_id: str = "default") -> str:
    """Insere uma entrega direto no banco (determinístico, sem endpoint)."""
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_persistence_model import DeliveryRecord

    delivery_id = f"dlv-{uuid.uuid4().hex[:12]}"
    db = DBSession(bind=engine)
    try:
        db.add(
            DeliveryRecord(
                delivery_id=delivery_id,
                tenant_id=tenant_id,
                order_id=f"ord-{uuid.uuid4().hex[:8]}",
                status="ASSIGNED",
                version=1,
                driver_id=driver_codigo,
            )
        )
        db.commit()
    finally:
        db.close()
    return delivery_id


# ── Cadastro + credencial ───────────────────────────────


def test_admin_creates_driver_and_returns_temp_password_once(client, admin_headers):
    driver_id, username, temp_password = _create_driver(client, admin_headers)
    assert driver_id and username and temp_password

    # A listagem NUNCA devolve a senha.
    listing = client.get("/admin/drivers", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    assert temp_password not in listing.text

    # Login pela auth principal + flag de troca obrigatória.
    login = _login(client, username, temp_password)
    assert login.status_code == 200, login.text
    assert login.json()["user"]["must_change_password"] is True


# ── Gate de troca de senha (HTTP + WS) ─────────────────


def test_pending_password_blocks_driver_route_and_ws(client, admin_headers):
    _, username, temp_password = _create_driver(client, admin_headers)
    token = _login(client, username, temp_password).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    blocked = client.get("/driver/deliveries", headers=headers)
    assert blocked.status_code == 403, blocked.text
    assert blocked.headers.get("X-GasFlow-Password-Change-Required") == "1"

    # Allowlist continua acessível.
    assert client.get("/auth/me", headers=headers).status_code == 200

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws?token={token}"):
            pass
    assert exc.value.code == 4003


def test_change_password_unlocks_driver_route_and_ws(client, admin_headers):
    driver_id, username, temp_password = _create_driver(client, admin_headers)
    token = _login(client, username, temp_password).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    changed = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": temp_password, "new_password": "NovaSenha123"},
    )
    assert changed.status_code == 200, changed.text

    ok = client.get("/driver/deliveries", headers=headers)
    assert ok.status_code == 200, ok.text
    assert "deliveries" in ok.json()

    # WS aceita a sessão do /auth/login e cai no canal driver:{codigo}.
    with client.websocket_connect(f"/ws?token={token}") as ws:
        welcome = ws.receive_json()
        assert welcome["type"] == "connected"
        assert welcome["channel"] == f"driver:{driver_id}"


# ── Isolamento de papéis ────────────────────────────────


def test_driver_and_admin_are_mutually_exclusive(client, admin_headers):
    _, username, temp_password = _create_driver(client, admin_headers)
    token = _login(client, username, temp_password).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": temp_password, "new_password": "NovaSenha123"},
    )

    # Entregador NÃO acessa rotas de admin.
    assert client.get("/admin/users", headers=headers).status_code == 403
    # Admin NÃO acessa /driver/*.
    assert client.get("/driver/deliveries", headers=admin_headers).status_code == 403


# ── Desativação invalida a sessão ───────────────────────


def test_deactivated_driver_session_is_revoked(client, admin_headers):
    driver_id, username, temp_password = _create_driver(client, admin_headers)
    token = _login(client, username, temp_password).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": temp_password, "new_password": "NovaSenha123"},
    )
    assert client.get("/driver/deliveries", headers=headers).status_code == 200

    deleted = client.delete(f"/admin/drivers/{driver_id}", headers=admin_headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["revoked_sessions"] >= 1

    # Sessão revogada → 401.
    assert client.get("/driver/deliveries", headers=headers).status_code == 401


# ── Escopo: só as entregas do próprio driver/tenant ─────


def test_driver_deliveries_are_scoped_by_driver_and_tenant(client, admin_headers):
    driver_id, username, temp_password = _create_driver(client, admin_headers)
    token = _login(client, username, temp_password).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": temp_password, "new_password": "NovaSenha123"},
    )

    mine = _insert_delivery(driver_id)
    other = _insert_delivery("999998")  # outro entregador

    res = client.get("/driver/deliveries", headers=headers)
    assert res.status_code == 200, res.text
    ids = [d["id"] for d in res.json()["deliveries"]]
    assert mine in ids
    assert other not in ids


# ── Perfil do entregador (token novo) ───────────────────


def test_driver_me_returns_profile_after_gate(client, admin_headers):
    driver_id, username, temp_password = _create_driver(client, admin_headers, name="Perfil Teste")
    token = _login(client, username, temp_password).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Com a troca pendente, o perfil também está fora da allowlist.
    assert client.get("/driver/me", headers=headers).status_code == 403

    client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": temp_password, "new_password": "NovaSenha123"},
    )
    me = client.get("/driver/me", headers=headers)
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["driver_id"] == driver_id
    assert body["name"] == "Perfil Teste"
    assert "tracking_interval_seconds" in body
    assert "work_hours" in body
