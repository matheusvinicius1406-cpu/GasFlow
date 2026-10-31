"""SEC-01C — Proteção de gerenciamento global de tenants.

Achados corrigidos (pré-`d135caf`):

1. `GET /auth/tenants` exigia apenas `require_admin` — qualquer ADMIN de
   qualquer empresa enumerava todas as empresas do deploy (enumeração
   cross-tenant).
2. `POST /auth/tenants` idem — qualquer admin criava tenants novos e
   `auth.create_tenant` o associava ADMINISTRADOR ao tenant criado
   (membership automática) → spawn de empresas sob controle alheio.

Fix: os dois endpoints exigem `require_admin` (autorização administrativa
preservada) E `is_platform_admin(ctx)` (escopo de plataforma, validado no
contexto da sessão — token + membership do banco; nunca no corpo da
requisição). Contrato legítimo de criação inalterado para plataforma.

Heurística SEC-01B preservada (documentada como risco residual): ADMIN
não-bootstrap do tenant `default` também atende `is_platform_admin`.

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
ADMIN_PW = "Sec01cAdminPass1!"
USER_PW = "Sec01cUserPass1!"
SYSTEM_PW = "Sec01cSystemPass1!"

PLATFORM_DETAIL = "Tenant management requires platform administrator"
ADMIN_DETAIL = "Admin access required"


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


def _db_scalar(sql: str, params: dict | None = None):
    from app.infrastructure.database.init_db import engine

    with engine.connect() as conn:
        return conn.execute(text(sql), params or {}).scalar()


def _db_exec(sql: str, params: dict | None = None) -> int:
    from app.infrastructure.database.init_db import engine

    with engine.begin() as conn:
        result = conn.execute(text(sql), params or {})
        return result.rowcount


@pytest.fixture(scope="module")
def env(client):
    """Cenário: bootstrap root (default) + SYSTEM + empresa A + OPERATOR default.

    Logins no fixture limitados a 4 (middleware LOGIN = 5/5min globais);
    usuários que precisam de token fora do fixture (nonboot_d, nomem) logam
    dentro do próprio teste — o conftest limpa o rate-limiter por teste.
    """

    def _create_user(client, root_headers, username, role, tenant_id, password):
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
        return {"user_id": res.json()["user_id"], "username": username, "password": password}

    suffix = uuid.uuid4().hex[:8]

    # Bootstrap root (admin-001, tenant default).
    root_token = _login(client, "admin", ROOT_PW)["token"]
    root_headers = _headers(root_token)

    # Empresa A (criada pelo bootstrap — provisionamento legítimo).
    tenant_a = f"c1ca_{suffix}"
    res = client.post("/auth/tenants", headers=root_headers, json={"tenant_id": tenant_a, "name": "Empresa A"})
    assert res.status_code == 200, res.text

    admin_a = _create_user(client, root_headers, f"adma_{suffix}", "ADMIN", tenant_a, ADMIN_PW)
    admin_a["headers"] = _headers(_login(client, admin_a["username"], ADMIN_PW)["token"])

    # SYSTEM legítimo no tenant de plataforma.
    system = _create_user(client, root_headers, f"sysc_{suffix}", "SYSTEM", "default", SYSTEM_PW)
    system["headers"] = _headers(_login(client, system["username"], SYSTEM_PW)["token"])

    # OPERATOR comum no tenant de plataforma (membership ≠ privilégio).
    operator_d = _create_user(client, root_headers, f"oprc_{suffix}", "OPERATOR", "default", USER_PW)
    operator_d["headers"] = _headers(_login(client, operator_d["username"], USER_PW)["token"])

    # ADMIN não-bootstrap em default (política temporária R2 do SEC-01B) e
    # usuário que ficará sem membership — login dentro dos testes.
    nonboot_d = _create_user(client, root_headers, f"nbad_{suffix}", "ADMIN", "default", ADMIN_PW)
    nomem = _create_user(client, root_headers, f"nomc_{suffix}", "ADMIN", "default", USER_PW)

    return {
        "suffix": suffix,
        "root_headers": root_headers,
        "root_user_id": _db_scalar("SELECT id FROM auth_users WHERE username = 'admin'"),
        "tenant_a": tenant_a,
        "admin_a": admin_a,
        "system": system,
        "operator_d": operator_d,
        "nonboot_d": nonboot_d,
        "nomem": nomem,
    }


def test_bootstrap_lists_and_creates_tenants(client, env):
    """Bootstrap admin-001 (default) lista e cria — provisionamento preservado."""
    res = client.get("/auth/tenants", headers=env["root_headers"])
    assert res.status_code == 200, res.text
    ids = [t["id"] for t in res.json()["tenants"]]
    assert "default" in ids

    tid = f"c1cbs_{env['suffix']}"
    res = client.post("/auth/tenants", headers=env["root_headers"], json={"tenant_id": tid, "name": "Bootstrap Spawn"})
    assert res.status_code == 200, res.text
    assert res.json() == {"success": True, "tenant_id": tid}


def test_system_lists_and_creates_tenants(client, env):
    """SystemRole.SYSTEM (admin global) lista e cria — provisionamento preservado."""
    res = client.get("/auth/tenants", headers=env["system"]["headers"])
    assert res.status_code == 200, res.text

    tid = f"c1csys_{env['suffix']}"
    res = client.post(
        "/auth/tenants", headers=env["system"]["headers"], json={"tenant_id": tid, "name": "System Spawn"}
    )
    assert res.status_code == 200, res.text
    assert res.json() == {"success": True, "tenant_id": tid}


def test_tenant_admin_cannot_list_tenants(client, env):
    """Enumeração cross-tenant bloqueada: admin da empresa A não lista empresas."""
    res = client.get("/auth/tenants", headers=env["admin_a"]["headers"])
    assert res.status_code == 403, res.text
    assert res.json()["detail"] == PLATFORM_DETAIL


def test_tenant_admin_cannot_create_tenant(client, env):
    """Spawn bloqueado: admin da empresa A não cria empresas novas."""
    tid = f"c1cx_{env['suffix']}"
    res = client.post(
        "/auth/tenants", headers=env["admin_a"]["headers"], json={"tenant_id": tid, "name": "Spawn Alheio"}
    )
    assert res.status_code == 403, res.text
    assert res.json()["detail"] == PLATFORM_DETAIL

    # E o tenant realmente não existe (nem o guard falhou em falso).
    ids = [t["id"] for t in client.get("/auth/tenants", headers=env["root_headers"]).json()["tenants"]]
    assert tid not in ids


def test_tenant_admin_cannot_create_default(client, env):
    """ADMIN de empresa A não cria 'default' — o guard dispara ANTES do 400
    de duplicata (a autorização nunca depende do tenant pedido no corpo)."""
    res = client.post(
        "/auth/tenants",
        headers=env["admin_a"]["headers"],
        json={"tenant_id": "default", "name": "Hijack"},
    )
    assert res.status_code == 403, res.text
    assert res.json()["detail"] == PLATFORM_DETAIL


def test_operator_in_default_cannot_list_or_create(client, env):
    """Membership em `default` não é privilégio: OPERATOR é barrado em GET e
    POST (autorização administrativa falha antes do guard de plataforma)."""
    headers = env["operator_d"]["headers"]

    res = client.get("/auth/tenants", headers=headers)
    assert res.status_code == 403, res.text
    assert res.json()["detail"] == ADMIN_DETAIL

    res = client.post("/auth/tenants", headers=headers, json={"tenant_id": f"c1cop_{env['suffix']}", "name": "Nope"})
    assert res.status_code == 403, res.text
    assert res.json()["detail"] == ADMIN_DETAIL


def test_user_without_membership_cannot_access(client, env):
    """Sem membership válida (revogada) não há papel nem permissões — os dois
    endpoints respondem 403 de autorização administrativa."""
    user_id = env["nomem"]["user_id"]
    headers = _headers(_login(client, env["nomem"]["username"], USER_PW)["token"])

    # Warm do caminho autenticado + revogação direta (não há endpoint de
    # revogação — mesmo artifício do SEC-01B).
    assert client.get("/auth/tenants", headers=headers).status_code == 200
    removed = _db_exec("DELETE FROM auth_memberships WHERE user_id = :uid", {"uid": user_id})
    assert removed >= 1

    res = client.get("/auth/tenants", headers=headers)
    assert res.status_code == 403, res.text
    assert res.json()["detail"] == ADMIN_DETAIL

    res = client.post("/auth/tenants", headers=headers, json={"tenant_id": f"c1cnm_{env['suffix']}", "name": "Nope"})
    assert res.status_code == 403, res.text
    assert res.json()["detail"] == ADMIN_DETAIL


def test_nonbootstrap_admin_in_default_is_platform_by_policy(client, env):
    """POLÍTICA TEMPORÁRIA SEC-01B (risco residual documentado): ADMIN
    não-bootstrap do tenant `default` atende `is_platform_admin` e por isso
    lista/cria. Este teste DOCUMENTA a heurística — a mitigação futura é a
    flag `is_platform` (migration própria, fora do SEC-01C)."""
    user_id = env["nonboot_d"]["user_id"]
    headers = _headers(_login(client, env["nonboot_d"]["username"], ADMIN_PW)["token"])

    res = client.get("/auth/tenants", headers=headers)
    assert res.status_code == 200, res.text

    tid = f"c1cnd_{env['suffix']}"
    res = client.post("/auth/tenants", headers=headers, json={"tenant_id": tid, "name": "Default Admin Spawn"})
    assert res.status_code == 200, res.text
    assert res.json() == {"success": True, "tenant_id": tid}

    # Membership automática do criador = ADMIN do novo tenant (contrato
    # legítimo de `create_tenant` preservado).
    count = _db_scalar(
        "SELECT COUNT(*) FROM auth_memberships m JOIN auth_roles r ON m.role_id = r.id "
        "WHERE m.user_id = :uid AND m.tenant_id = :tid AND r.name = 'ADMIN'",
        {"uid": user_id, "tid": tid},
    )
    assert count == 1


def test_legit_creation_keeps_creator_admin_membership(client, env):
    """Criação legítima (bootstrap) mantém a membership automática prevista."""
    tid = f"c1cm_{env['suffix']}"
    res = client.post("/auth/tenants", headers=env["root_headers"], json={"tenant_id": tid, "name": "Com Membership"})
    assert res.status_code == 200, res.text

    count = _db_scalar(
        "SELECT COUNT(*) FROM auth_memberships m JOIN auth_roles r ON m.role_id = r.id "
        "WHERE m.user_id = :uid AND m.tenant_id = :tid AND r.name = 'ADMIN'",
        {"uid": env["root_user_id"], "tid": tid},
    )
    assert count == 1


def test_duplicate_tenant_returns_controlled_400(client, env):
    """Tenant duplicado continua erro controlado (400) para plataforma —
    contrato de criação inalterado."""
    tid = f"c1cdup_{env['suffix']}"
    res = client.post("/auth/tenants", headers=env["root_headers"], json={"tenant_id": tid, "name": "Dup A"})
    assert res.status_code == 200, res.text

    res = client.post("/auth/tenants", headers=env["root_headers"], json={"tenant_id": tid, "name": "Dup B"})
    assert res.status_code == 400, res.text
    assert "already exists" in res.json()["detail"]


def test_cross_tenant_remains_isolated_after_creation(client, env):
    """Após criação legítima, o isolamento vale: admin da empresa A não
    alcança usuário recém-criado em outro tenant (404, não 403/200)."""
    tid = f"c1cxi_{env['suffix']}"
    res = client.post("/auth/tenants", headers=env["root_headers"], json={"tenant_id": tid, "name": "Isolada"})
    assert res.status_code == 200, res.text

    # Usuário no tenant novo (provisionamento de plataforma, permitido).
    res = client.post(
        "/auth/users",
        headers=env["root_headers"],
        json={
            "username": f"xiusr_{env['suffix']}",
            "email": f"xiusr_{env['suffix']}@gasflow.local",
            "password": USER_PW,
            "display_name": "xiusr",
            "role": "OPERATOR",
            "tenant_id": tid,
        },
    )
    assert res.status_code == 200, res.text
    other_user_id = res.json()["user_id"]

    # Admin da empresa A: PATCH cross-tenant → 404 (escopo de tenant intacto).
    res = client.patch(
        f"/admin/users/{other_user_id}",
        headers=env["admin_a"]["headers"],
        json={"display_name": "hijacked"},
    )
    assert res.status_code == 404, res.text


def test_get_post_auth_errors_consistent(client, env):
    """Mesmo ator recebe o mesmo detail em GET e POST (consistência de erro)."""
    res_get = client.get("/auth/tenants", headers=env["admin_a"]["headers"])
    res_post = client.post(
        "/auth/tenants",
        headers=env["admin_a"]["headers"],
        json={"tenant_id": f"c1cic_{env['suffix']}", "name": "Consistent"},
    )
    assert res_get.status_code == res_post.status_code == 403
    assert res_get.json()["detail"] == res_post.json()["detail"] == PLATFORM_DETAIL
