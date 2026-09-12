"""Testes de integração dos endpoints admin (P0 3.3).

Cobre: 403 sem permissão, criação com audit, reset-password (flag +
senha única vez), soft delete, matriz de permissões do role (persistência
+ invalidação de cache) e filtros de auditoria.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200
    return res.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _create_operator(client, admin_headers) -> str:
    """Cria usuário OPERATOR e retorna (token, user_id)."""
    from app.infrastructure.database.init_db import engine
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    db = Session(bind=engine)
    try:
        role_id = db.execute(text("SELECT id FROM auth_roles WHERE name = 'OPERATOR'")).scalar_one()
    finally:
        db.close()

    username = f"op_{uuid.uuid4().hex[:8]}"
    res = client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": username,
            "email": f"{username}@gasflow.local",
            "password": "InitialPass1!",
            "role": "OPERATOR",
        },
    )
    assert res.status_code == 201, res.text
    user_id = res.json()["user_id"]

    login = client.post("/auth/login", json={"username": username, "password": "InitialPass1!"})
    assert login.status_code == 200, login.text
    return login.json()["token"], user_id


# ── 403 sem permissão ───────────────────────────────────


def test_operator_cannot_create_users(client, admin_headers):
    token, _ = _create_operator(client, admin_headers)
    res = client.post(
        "/admin/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "nope_user",
            "email": "nope@gasflow.local",
            "password": "Whatever1!",
            "role": "OPERATOR",
        },
    )
    assert res.status_code == 403


def test_operator_cannot_read_audit(client, admin_headers):
    token, _ = _create_operator(client, admin_headers)
    res = client.get("/admin/audit", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_unauthenticated_admin_401(client):
    assert client.get("/admin/users").status_code == 401


# ── Criação + audit ─────────────────────────────────────


def test_create_user_with_permission_201_and_audit(client, admin_headers):
    username = f"adm_{uuid.uuid4().hex[:8]}"
    res = client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": username,
            "email": f"{username}@gasflow.local",
            "password": "StrongPass1!",
            "display_name": "Criado no teste",
            "role": "OPERATOR",
        },
    )
    assert res.status_code == 201, res.text
    user_id = res.json()["user_id"]

    # Audit gravado com after_json (sem password).
    audit = client.get("/admin/audit", headers=admin_headers, params={"action": "USER_CREATED"}).json()["records"]
    entry = next(r for r in audit if r["resource_id"] == user_id)
    assert entry["after_json"]["username"] == username
    assert "password" not in (entry["after_json"] or {})

    # Usuário criado com must_change_password=True.
    users = client.get("/admin/users", headers=admin_headers, params={"search": username}).json()["users"]
    assert users[0]["must_change_password"] is True


def test_create_user_duplicate_username_400(client, admin_headers):
    body = {
        "username": f"dup_{uuid.uuid4().hex[:6]}",
        "email": "dup@gasflow.local",
        "password": "StrongPass1!",
        "role": "OPERATOR",
    }
    assert client.post("/admin/users", headers=admin_headers, json=body).status_code == 201
    assert client.post("/admin/users", headers=admin_headers, json=body).status_code == 400


# ── Reset password ──────────────────────────────────────


def test_reset_password_sets_must_change_flag(client, admin_headers):
    _, user_id = _create_operator(client, admin_headers)

    res = client.post(f"/admin/users/{user_id}/reset-password", headers=admin_headers)
    assert res.status_code == 200
    temp_password = res.json()["temporary_password"]
    assert res.json()["must_change_password"] is True

    # Login com a senha temporária funciona.
    users = client.get("/admin/users", headers=admin_headers).json()["users"]
    username = next(u["username"] for u in users if u["id"] == user_id)
    login = client.post("/auth/login", json={"username": username, "password": temp_password})
    assert login.status_code == 200

    # Audit NÃO contém a senha em texto puro.
    audit = client.get(
        "/admin/audit",
        headers=admin_headers,
        params={"action": "PASSWORD_CHANGED", "actor_id": "admin-001"},
    ).json()["records"]
    serialized = str(audit)
    assert temp_password not in serialized
    assert "password_hash" not in serialized


def test_reset_password_404(client, admin_headers):
    res = client.post(f"/admin/users/{uuid.uuid4()}/reset-password", headers=admin_headers)
    assert res.status_code == 404


# ── Soft delete ─────────────────────────────────────────


def test_deactivate_user_soft_delete(client, admin_headers):
    _, user_id = _create_operator(client, admin_headers)

    res = client.post(f"/admin/users/{user_id}/deactivate", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["user"]["status"] == "DISABLED"

    # Usuário desativado não loga mais.
    users = client.get("/admin/users", headers=admin_headers).json()["users"]
    username = next(u["username"] for u in users if u["id"] == user_id)
    assert client.post("/auth/login", json={"username": username, "password": "InitialPass1!"}).status_code == 401

    # Registro continua no banco (soft delete, sem perda de auditoria).
    detail = next(u for u in users if u["id"] == user_id)
    assert detail["status"] == "DISABLED"

    # Auto-desativação é bloqueada.
    me = client.get("/auth/me", headers=admin_headers).json()
    assert client.post(f"/admin/users/{me['id']}/deactivate", headers=admin_headers).status_code == 400


# ── Roles / matriz ──────────────────────────────────────


def test_update_role_permissions_persists_and_audits(client, admin_headers):
    roles = client.get("/admin/roles", headers=admin_headers).json()["roles"]
    viewer = next(r for r in roles if r["name"] == "VIEWER")

    new_perms = ["order.read", "product.read", "inventory.read"]
    res = client.patch(
        f"/admin/roles/{viewer['id']}/permissions", headers=admin_headers, json={"permissions": new_perms}
    )
    assert res.status_code == 200, res.text
    assert sorted(res.json()["role"]["permissions"]) == sorted(new_perms)

    # Persistiu no JSON e na matriz normalizada.
    roles_after = client.get("/admin/roles", headers=admin_headers).json()["roles"]
    assert sorted(next(r for r in roles_after if r["name"] == "VIEWER")["permissions"]) == sorted(new_perms)

    # Audit com before/after.
    audit = client.get("/admin/audit", headers=admin_headers, params={"action": "ROLE_CHANGED"}).json()["records"]
    entry = next(r for r in audit if r["resource_id"] == viewer["id"])
    assert entry["before_json"]["permissions"] == viewer["permissions"]
    assert entry["after_json"]["permissions"] == sorted(new_perms)


def test_update_role_permissions_unknown_code_400(client, admin_headers):
    roles = client.get("/admin/roles", headers=admin_headers).json()["roles"]
    viewer = next(r for r in roles if r["name"] == "VIEWER")
    res = client.patch(
        f"/admin/roles/{viewer['id']}/permissions",
        headers=admin_headers,
        json={"permissions": ["nao.existe"]},
    )
    assert res.status_code == 400


def test_update_role_permissions_invalidates_cache(client, admin_headers):
    """Loader antes/depois da mutação: permissão nova vira efetiva sem 60s."""
    from app.application.security.permission_policy_loader import get_policy_loader
    from app.infrastructure.database.init_db import engine
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    db = Session(bind=engine)
    try:
        viewer_id = db.execute(text("SELECT id FROM auth_roles WHERE name = 'VIEWER'")).scalar_one()
        export_pid = db.execute(text("SELECT id FROM permissions WHERE code = 'finance.export_pdf'")).scalar_one()
    finally:
        db.close()

    get_policy_loader().invalidate_all()
    perms_before = get_policy_loader().load_for_role(viewer_id)
    assert "finance.export_pdf" not in perms_before

    res = client.patch(
        f"/admin/roles/{viewer_id}/permissions",
        headers=admin_headers,
        json={"permissions": ["order.read", "finance.export_pdf"]},
    )
    assert res.status_code == 200

    perms_after = get_policy_loader().load_for_role(viewer_id)
    assert "finance.export_pdf" in perms_after

    # Restaura estado para outros testes.
    client.patch(
        f"/admin/roles/{viewer_id}/permissions",
        headers=admin_headers,
        json={
            "permissions": [
                "customer.read",
                "order.read",
                "product.read",
                "inventory.read",
                "finance.read",
                "delivery.read",
                "settings.read",
            ]
        },
    )


# ── Audit filters ───────────────────────────────────────


def test_audit_log_filters_by_actor_and_period(client, admin_headers):
    # Duas mutações para filtrar.
    username = f"f_{uuid.uuid4().hex[:6]}"
    created = client.post(
        "/admin/users",
        headers=admin_headers,
        json={"username": username, "email": f"{username}@x.local", "password": "StrongPass1!", "role": "OPERATOR"},
    )
    assert created.status_code == 201

    # Filtro por ação.
    by_action = client.get("/admin/audit", headers=admin_headers, params={"action": "USER_CREATED"}).json()["records"]
    assert by_action and all(r["action"] == "USER_CREATED" for r in by_action)

    # Filtro por período (janela futura → vazio).
    future = client.get(
        "/admin/audit",
        headers=admin_headers,
        params={"from_ts": "2099-01-01T00:00:00", "to_ts": "2099-12-31T00:00:00"},
    ).json()["records"]
    assert future == []

    # Paginação.
    paged = client.get("/admin/audit", headers=admin_headers, params={"limit": 2, "offset": 0}).json()["records"]
    assert len(paged) <= 2
