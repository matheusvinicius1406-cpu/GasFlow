"""SEC-01B — Fechamento do isolamento multi-tenant e segurança administrativa.

Achados cobertos aqui (complementa as 14 provas do SEC-01, que continuam
valendo em `test_sec01_admin_tenant_isolation.py`):

1. Roles são GLOBAIS (`auth_roles`/`role_permissions` sem tenant_id):
   admin de uma empresa alterava permissões usadas por todas as outras.
2. `system_settings` é global por deploy: admin de uma empresa reconfigurava
   a operação das demais (escrita agora restrita a escopo de plataforma).
3. Provisionamento legado (`POST /auth/users`): `tenant_id` explícito de
   outra empresa e papel SYSTEM estavam abertos a qualquer admin (inclusive
   criação de conta no tenant de plataforma = via de escalação).
4. Autorização dependia do CACHE: `load_for_user` chaveava só por usuário —
   membership revogada/papel trocado mantinha o set antigo até o TTL (60s);
   um override de permissão não pode (e não deve) compensar membership
   ausente — a fronteira é a política compartilhada, não uma rota.
5. Username é único GLOBAL: conflito com conta de outra empresa no PATCH
   violava o unique e estourava 500 — agora 400 controlado.

Ambiente isolado: `conftest.py` redireciona o engine para SQLite temporário —
sem migrations e sem tocar em gasflow.db.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app

ROOT_PW = "test_password_123"
ADMIN_PW = "Sec01bAdminPass1!"
USER_PW = "Sec01bUserPass1!"
SYSTEM_PW = "Sec01bSystemPass1!"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _login(client, username: str, password: str) -> dict:
    res = client.post("/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["token"]
    return body


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _db_exec(sql: str, params: dict | None = None) -> int:
    from app.infrastructure.database.init_db import engine

    with engine.begin() as conn:
        result = conn.execute(text(sql), params or {})
        return result.rowcount


def _db_scalar(sql: str, params: dict | None = None):
    from app.infrastructure.database.init_db import engine

    with engine.connect() as conn:
        return conn.execute(text(sql), params or {}).scalar()


@pytest.fixture(scope="module")
def env(client):
    """Cenário: plataforma (root + SYSTEM) × tenant A × tenant B."""
    suffix = uuid.uuid4().hex[:8]
    tenant_a = f"sec01ba{suffix}"
    tenant_b = f"sec01bb{suffix}"

    root = _login(client, "admin", ROOT_PW)
    root_headers = _headers(root["token"])

    for tid in (tenant_a, tenant_b):
        res = client.post(
            "/auth/tenants",
            headers=root_headers,
            json={"tenant_id": tid, "name": f"SEC01B {tid}"},
        )
        assert res.status_code == 200, res.text

    def _mk_user(username: str, role: str, tenant_id: str, password: str) -> dict:
        res = client.post(
            "/auth/users",
            headers=root_headers,
            json={
                "username": username,
                "email": f"{username}@gasflow.local",
                "password": password,
                "display_name": username,
                "role": role,
                "tenant_id": tenant_id,
            },
        )
        assert res.status_code == 200, res.text
        # Sem login aqui de propósito: o middleware LOGIN é 5/5min globais —
        # o fixture usa 4 (root/admin_a/admin_b/system) e cada teste que
        # precisa de token limpa o bucket antes (conftest).
        return {"user_id": res.json()["user_id"], "username": username, "password": password}

    admin_a = _mk_user(f"a1ba_{suffix}", "ADMIN", tenant_a, ADMIN_PW)
    admin_a["headers"] = _headers(_login(client, admin_a["username"], ADMIN_PW)["token"])
    admin_b = _mk_user(f"a1bb_{suffix}", "ADMIN", tenant_b, ADMIN_PW)
    admin_b["headers"] = _headers(_login(client, admin_b["username"], ADMIN_PW)["token"])
    target_b = _mk_user(f"tgtb_{suffix}", "OPERATOR", tenant_b, USER_PW)
    # Admin global legítimo (SystemRole.SYSTEM) no tenant de plataforma.
    system = _mk_user(f"sysb_{suffix}", "SYSTEM", "default", SYSTEM_PW)
    system["headers"] = _headers(_login(client, system["username"], SYSTEM_PW)["token"])

    # Usuário do tenant A criado pelo próprio admin_a (alvo do conflito de
    # username; nasce com must_change_password — só usado como alvo de PATCH).
    res = client.post(
        "/admin/users",
        headers=admin_a["headers"],
        json={
            "username": f"owna_{suffix}",
            "email": f"owna_{suffix}@gasflow.local",
            "password": USER_PW,
            "display_name": "Proprio A",
            "role": "OPERATOR",
        },
    )
    assert res.status_code == 201, res.text
    own_a = {"user_id": res.json()["user_id"], "username": f"owna_{suffix}"}

    # Usuário ADMIN na plataforma (tenant default) para o teste de revogação
    # de membership (legacy cria sem must_change_password). Login acontece
    # dentro do teste — não gasta a janela de LOGIN do fixture.
    revoked = _mk_user(f"revk_{suffix}", "ADMIN", "default", USER_PW)

    roles = {r["name"]: r for r in client.get("/admin/roles", headers=root_headers).json()["roles"]}

    return {
        "suffix": suffix,
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "root_headers": root_headers,
        "admin_a": admin_a,
        "admin_b": admin_b,
        "target_b": target_b,
        "own_a": own_a,
        "system": system,
        "revoked": revoked,
        "roles": roles,
    }


# ── 1/2. Matriz global de permissões ────────────────────


def test_tenant_admin_cannot_change_global_role_permissions(client, env):
    """Admin de A não altera permissões globais usadas por B (403, sem efeito).

    O `require_permission("permission.assign")` sozinho não bastava: o ADMIN
    de empresa tem admin.* e passava pela checagem — o guard é de ESCOPO.
    """
    viewer_id = env["roles"]["VIEWER"]["id"]
    before = next(
        r for r in client.get("/admin/roles", headers=env["root_headers"]).json()["roles"] if r["id"] == viewer_id
    )

    res = client.patch(
        f"/admin/roles/{viewer_id}/permissions",
        headers=env["admin_a"]["headers"],
        json={"permissions": ["order.read"]},
    )
    assert res.status_code == 403, res.text
    assert "platform" in res.json()["detail"].lower()

    after = next(
        r for r in client.get("/admin/roles", headers=env["root_headers"]).json()["roles"] if r["id"] == viewer_id
    )
    assert after["permissions"] == before["permissions"], "matriz global foi alterada por admin de tenant"

    # O mesmo vale para o admin de B (espelho).
    res = client.patch(
        f"/admin/roles/{viewer_id}/permissions",
        headers=env["admin_b"]["headers"],
        json={"permissions": ["order.read"]},
    )
    assert res.status_code == 403, res.text


def test_global_admins_keep_role_permission_operations(client, env):
    """Administrador global legítimo (root de plataforma e SYSTEM) continua
    autorizado a mutar a matriz — mesmo contrato, ator correto."""
    viewer_id = env["roles"]["VIEWER"]["id"]
    current = next(
        r for r in client.get("/admin/roles", headers=env["root_headers"]).json()["roles"] if r["id"] == viewer_id
    )["permissions"]

    res = client.patch(
        f"/admin/roles/{viewer_id}/permissions",
        headers=env["root_headers"],
        json={"permissions": current},
    )
    assert res.status_code == 200, res.text

    res = client.patch(
        f"/admin/roles/{viewer_id}/permissions",
        headers=env["system"]["headers"],
        json={"permissions": current},
    )
    assert res.status_code == 200, res.text


# ── 3. Configurações globais (system_settings é global por deploy) ──


def test_tenant_admin_cannot_modify_global_settings(client, env):
    """Admin de A não modifica configurações globais — as mesmas que B lê.

    `system_settings` não tem tenant_id (SettingsService: "global por
    deploy"): escrita de A reconfiguraria B. Leitura permanece liberada.
    """
    key = "site_name"
    original = client.get(f"/settings/key/{key}", headers=env["root_headers"])
    assert original.status_code == 200, original.text
    original_value = original.json()["value"]

    # Escrita por A bloqueada (mesmo tendo admin.* / settings.write).
    res = client.put(f"/settings/key/{key}", headers=env["admin_a"]["headers"], json={"value": "HACKED PELA A"})
    assert res.status_code == 403, res.text
    res = client.post("/settings/seed", headers=env["admin_a"]["headers"])
    assert res.status_code == 403, res.text

    # Nenhum efeito colateral: valor global intacto para B e para todos.
    after = client.get(f"/settings/key/{key}", headers=env["root_headers"])
    assert after.status_code == 200
    assert after.json()["value"] == original_value

    # Leitura legítima de A preservada.
    res = client.get(f"/settings/key/{key}", headers=env["admin_a"]["headers"])
    assert res.status_code == 200, res.text

    # Caminho de plataforma continua funcionando (re-grava o MESMO valor).
    res = client.put(f"/settings/key/{key}", headers=env["root_headers"], json={"value": original_value})
    assert res.status_code == 200, res.text


# ── 4. Membership revogada × override de permissão ──────


def test_revoked_membership_loses_access_despite_permission_override(client, env):
    """Cache quente com papel ADMIN + override explícito + membership revogada.

    Pré-condição do bug (SEC-01B): `load_for_user` era chaveado só por
    usuário — o set de `admin.*` vivia no cache até o TTL e o `require_permission`
    passava sem membership. A fronteira agora é a política compartilhada
    (`validate_token` + chave de cache por papel): sem membership, sem
    permissões — override não compensa.
    """
    user_id = env["revoked"]["user_id"]
    headers = _headers(_login(client, env["revoked"]["username"], env["revoked"]["password"])["token"])

    # 1) Cache quente com papel ADMIN (200 = admin.* efetivo).
    res = client.get("/admin/users", headers=headers)
    assert res.status_code == 200, res.text

    # 2) Override explícito de user.read (registrado no banco).
    granted = _db_exec(
        "INSERT INTO user_permissions_override (user_id, permission_id, granted, created_by, created_at) "
        "SELECT :uid, id, 1, 'sec01b', datetime('now') FROM permissions WHERE code = 'user.read' "
        "AND NOT EXISTS (SELECT 1 FROM user_permissions_override o "
        "WHERE o.user_id = :uid AND o.permission_id = (SELECT id FROM permissions WHERE code = 'user.read'))",
        {"uid": user_id},
    )
    assert granted == 1
    assert _db_scalar("SELECT COUNT(*) FROM user_permissions_override WHERE user_id = :uid", {"uid": user_id}) >= 1

    # 3) Revoga a membership (não há endpoint de revogação — remoção direta,
    #    único caminho existente; ver docstring de deactivate_user).
    _db_exec("DELETE FROM auth_memberships WHERE user_id = :uid", {"uid": user_id})
    assert _db_scalar("SELECT COUNT(*) FROM auth_memberships WHERE user_id = :uid", {"uid": user_id}) == 0

    # 4) Sessão segue viva (allowlist de /auth), mas sem autorização alguma:
    #    nem o cache anterior, nem o override, nem admin.* sobrevivem.
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["role"] == "OPERATOR"

    res = client.get("/admin/users", headers=headers)
    assert res.status_code == 403, res.text
    res = client.get("/admin/roles", headers=headers)
    assert res.status_code == 403, res.text
    res = client.put("/settings/key/site_name", headers=headers, json={"value": "X"})
    assert res.status_code == 403, res.text


def test_user_without_membership_gains_no_access_by_override(client, env):
    """Usuário que NUNCA teve membership no tenant da sessão: override de
    permissão não abre porta — 403 em toda superfície administrativa."""
    suffix = env["suffix"]
    username = f"nomem_{suffix}"
    res = client.post(
        "/auth/users",
        headers=env["root_headers"],
        json={
            "username": username,
            "email": f"{username}@gasflow.local",
            "password": USER_PW,
            "display_name": "Sem Membership",
            "role": "OPERATOR",
            "tenant_id": "default",
        },
    )
    assert res.status_code == 200, res.text
    user_id = res.json()["user_id"]

    _db_exec("DELETE FROM auth_memberships WHERE user_id = :uid", {"uid": user_id})
    _db_exec(
        "INSERT INTO user_permissions_override (user_id, permission_id, granted, created_by, created_at) "
        "SELECT :uid, id, 1, 'sec01b', datetime('now') FROM permissions WHERE code = 'user.read'",
        {"uid": user_id},
    )

    headers = _headers(_login(client, username, USER_PW)["token"])
    assert client.get("/admin/users", headers=headers).status_code == 403
    assert client.get("/admin/audit", headers=headers).status_code == 403
    # Leitura pública de papel (qualquer autenticado) segue respondendo.
    assert client.get("/auth/roles", headers=headers).status_code == 200


# ── 5. Provisionamento legado global (/auth/users) ──────


def test_tenant_admin_cannot_provision_cross_tenant_or_system_accounts(client, env):
    """Operações globais de conta no endpoint legado exigem escopo de
    plataforma: cross-tenant (inclusive o tenant `default`), papel SYSTEM."""
    base = {
        "username": f"ill_{env['suffix']}",
        "email": f"ill_{env['suffix']}@gasflow.local",
        "password": USER_PW,
        "display_name": "Illegal",
    }

    # Outra empresa.
    res = client.post(
        "/auth/users",
        headers=env["admin_a"]["headers"],
        json={**base, "role": "OPERATOR", "tenant_id": env["tenant_b"]},
    )
    assert res.status_code == 403, res.text

    # Tenant de plataforma (via de escalação para admin de `default`).
    res = client.post(
        "/auth/users",
        headers=env["admin_a"]["headers"],
        json={**base, "role": "ADMIN", "tenant_id": "default"},
    )
    assert res.status_code == 403, res.text

    # Papel global SYSTEM no próprio tenant.
    res = client.post(
        "/auth/users",
        headers=env["admin_a"]["headers"],
        json={**base, "role": "SYSTEM", "tenant_id": env["tenant_a"]},
    )
    assert res.status_code == 403, res.text

    # Positivo: provisionar no PRÓPRIO tenant continua legítimo.
    own_username = f"legit_{env['suffix']}"
    res = client.post(
        "/auth/users",
        headers=env["admin_a"]["headers"],
        json={
            "username": own_username,
            "email": f"{own_username}@gasflow.local",
            "password": USER_PW,
            "display_name": "Legit",
            "role": "OPERATOR",
            "tenant_id": env["tenant_a"],
        },
    )
    assert res.status_code == 200, res.text
    members = _db_scalar(
        "SELECT COUNT(*) FROM auth_memberships WHERE user_id = :uid AND tenant_id = :tid",
        {"uid": res.json()["user_id"], "tid": env["tenant_a"]},
    )
    assert members == 1

    # Positivo: o root de plataforma provisiona cross-tenant (bootstrap).
    res = client.post(
        "/auth/users",
        headers=env["root_headers"],
        json={
            "username": f"rootx_{env['suffix']}",
            "email": f"rootx_{env['suffix']}@gasflow.local",
            "password": USER_PW,
            "display_name": "Root Cross",
            "role": "OPERATOR",
            "tenant_id": env["tenant_b"],
        },
    )
    assert res.status_code == 200, res.text


# ── 6. Username global duplicado → 400 controlado ───────


def test_duplicate_username_returns_400_not_500(client, env):
    """Unicidade global de username preservada; o conflito não vaza 500."""
    # PATCH para username de OUTRA empresa (antes: IntegrityError → 500).
    res = client.patch(
        f"/admin/users/{env['own_a']['user_id']}",
        headers=env["admin_a"]["headers"],
        json={"username": env["target_b"]["username"]},
    )
    assert res.status_code == 400, res.text
    assert res.json()["detail"] == "Username already exists"
    assert "Traceback" not in res.text and "IntegrityError" not in res.text

    # Nada mudou nos dois lados.
    users_a = client.get("/admin/users", headers=env["admin_a"]["headers"]).json()["users"]
    row_own = next(u for u in users_a if u["id"] == env["own_a"]["user_id"])
    assert row_own["username"] == env["own_a"]["username"]
    users_b = client.get("/admin/users", headers=env["admin_b"]["headers"]).json()["users"]
    assert next(u for u in users_b if u["id"] == env["target_b"]["user_id"])["username"] == env["target_b"]["username"]

    # Mesmo conflito no endpoint legado de criação → 400 (contrato existente).
    res = client.post(
        "/auth/users",
        headers=env["root_headers"],
        json={
            "username": env["target_b"]["username"],
            "email": "dup@gasflow.local",
            "password": USER_PW,
            "role": "OPERATOR",
            "tenant_id": env["tenant_b"],
        },
    )
    assert res.status_code == 400, res.text
    assert res.json()["detail"] == "Username already exists"

    # E na criação via /admin/users (pre-check do próprio router).
    res = client.post(
        "/admin/users",
        headers=env["admin_a"]["headers"],
        json={
            "username": env["own_a"]["username"],
            "email": "dup2@gasflow.local",
            "password": USER_PW,
            "role": "OPERATOR",
        },
    )
    assert res.status_code == 400, res.text
    assert res.json()["detail"] == "Username already exists"


# ── 7. Leituras legítimas preservadas ───────────────────


def test_tenant_admin_keeps_reads_and_member_mutations(client, env):
    """Controles consistentes sem mudar o comportamento legítimo: leitura de
    catálogo/auditoria/config e mutações de usuário do PRÓPRIO tenant."""
    assert client.get("/admin/roles", headers=env["admin_a"]["headers"]).status_code == 200
    assert client.get("/admin/audit", headers=env["admin_a"]["headers"]).status_code == 200
    assert client.get("/settings", headers=env["admin_a"]["headers"]).status_code == 200

    # Mutação de usuário no próprio tenant segue funcionando.
    res = client.post(
        f"/admin/users/{env['own_a']['user_id']}/deactivate",
        headers=env["admin_a"]["headers"],
    )
    assert res.status_code == 200, res.text
    res = client.post(
        f"/admin/users/{env['own_a']['user_id']}/activate",
        headers=env["admin_a"]["headers"],
    )
    assert res.status_code == 200, res.text
