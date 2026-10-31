"""SEC-01 — Isolamento multi-tenant nas operações administrativas (`/admin/*`).

Auditoria SEC-01: a superfície `admin.py` operava sobre `auth_users` (tabela
GLOBAL — não tem `tenant_id`) sem checar `auth_memberships`. Qualquer admin
de uma empresa listava, editava, reseta senha e desativava usuários de
outras empresas (IDOR cross-tenant); o reset de senha do entregador ainda
batia na credencial errada porque `auth_users.driver_id` guarda o `codigo`,
sequencial POR TENANT (duas empresas têm "000001").

Este módulo cobre, com casos negativos entre tenants:
- listagem (`GET /admin/users`), edição (`PATCH`), redefinição de senha,
  ativação e desativação: alvo de outro tenant → 404, sem efeito colateral;
- ator sem membership no tenant da sessão → 403 (helpers unitários);
- usuário multi-tenant (membro dos dois tenants) gerenciável pelos dois;
- preservação do administrador global legítimo (`SystemRole.SYSTEM`);
- bloqueio de cunhagem do papel global a partir da administração por tenant;
- credenciais de entregador escopadas pelo tenant (listagem + reset).

Ambiente isolado: `conftest.py` redireciona o engine para SQLite temporário —
sem migrations e sem tocar em gasflow.db.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app

ADMIN_PW = "Sec01AdminPass1!"
TARGET_PW = "Sec01TargetPass1!"
SYSTEM_PW = "Sec01SystemPass1!"


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


@pytest.fixture(scope="module")
def env(client):
    """Dois tenants isolados + admins + alvos + entregadores + admin global.

    Montado uma vez por módulo (bcrypt + chamadas HTTP); os testes rodam em
    ordem de definição e contam com este estado.
    """
    suffix = uuid.uuid4().hex[:8]
    tenant_a = f"sec01a{suffix}"
    tenant_b = f"sec01b{suffix}"

    # ── bootstrap root (admin-001, tenant default) ──
    root_token = _login(client, "admin", "test_password_123")["token"]
    root_headers = _headers(root_token)

    for tid in (tenant_a, tenant_b):
        res = client.post(
            "/auth/tenants",
            headers=root_headers,
            json={"tenant_id": tid, "name": f"SEC01 {tid}"},
        )
        assert res.status_code == 200, res.text

    def _mk_admin(username: str, tenant_id: str) -> dict:
        # Endpoint legado /auth/users aceita tenant_id explícito e cria a
        # membership — caminho curto para provisionar um admin de empresa.
        res = client.post(
            "/auth/users",
            headers=root_headers,
            json={
                "username": username,
                "email": f"{username}@gasflow.local",
                "password": ADMIN_PW,
                "display_name": f"Admin {tenant_id}",
                "role": "ADMIN",
                "tenant_id": tenant_id,
            },
        )
        assert res.status_code == 200, res.text
        user_id = res.json()["user_id"]
        token = _login(client, username, ADMIN_PW)["token"]
        return {"user_id": user_id, "username": username, "headers": _headers(token)}

    admin_a = _mk_admin(f"adma_{suffix}", tenant_a)
    admin_b = _mk_admin(f"admb_{suffix}", tenant_b)

    def _mk_target(admin: dict, username: str, display_name: str) -> dict:
        res = client.post(
            "/admin/users",
            headers=admin["headers"],
            json={
                "username": username,
                "email": f"{username}@gasflow.local",
                "password": TARGET_PW,
                "display_name": display_name,
                "role": "OPERATOR",
            },
        )
        assert res.status_code == 201, res.text
        return {"user_id": res.json()["user_id"], "username": username, "password": TARGET_PW}

    target_a = _mk_target(admin_a, f"tgta_{suffix}", "Alvo Empresa A")
    own_a = _mk_target(admin_a, f"owna_{suffix}", "Proprio Empresa A")
    target_b = _mk_target(admin_b, f"tgtb_{suffix}", "Alvo Empresa B")
    toggle_b = _mk_target(admin_b, f"tglb_{suffix}", "Toggle Empresa B")

    # Usuário multi-tenant: criado em A, membership extra em B inserida
    # direto no DB (nenhum endpoint concede membership cruzada hoje).
    multi = _mk_target(admin_a, f"mtla_{suffix}", "Multi Tenant")
    _add_membership(multi["user_id"], tenant_b, "OPERATOR")

    # Entregadores: ordem A → B de propósito. Os dois tenants geram o MESMO
    # codigo ("000001" — sequencial por tenant) e usernames distintos; criar
    # A primeiro faz o bug pré-correção (query global) expor/reseter a
    # credencial errada — capturado pelos testes de driver.
    driver_a = _mk_driver(client, admin_a, f"drva_{suffix}", "11970000001")
    driver_b = _mk_driver(client, admin_b, f"drvb_{suffix}", "21970000001")
    assert driver_a["driver_id"] == driver_b["driver_id"], (
        "cenario pressupoe mesmo codigo (000001) em tenants distintos"
    )

    # Admin global legítimo (SystemRole.SYSTEM) em default, via endpoint legado.
    system_username = f"sysg_{suffix}"
    res = client.post(
        "/auth/users",
        headers=root_headers,
        json={
            "username": system_username,
            "email": f"{system_username}@gasflow.local",
            "password": SYSTEM_PW,
            "display_name": "Global SYSTEM",
            "role": "SYSTEM",
            "tenant_id": "default",
        },
    )
    assert res.status_code == 200, res.text
    system_token = _login(client, system_username, SYSTEM_PW)["token"]
    system = {"user_id": res.json()["user_id"], "username": system_username, "headers": _headers(system_token)}

    roles = {r["name"]: r["id"] for r in client.get("/admin/roles", headers=root_headers).json()["roles"]}

    return {
        "suffix": suffix,
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "admin_a": admin_a,
        "admin_b": admin_b,
        "target_a": target_a,
        "own_a": own_a,
        "target_b": target_b,
        "toggle_b": toggle_b,
        "multi": multi,
        "driver_a": driver_a,
        "driver_b": driver_b,
        "system": system,
        "role_ids": roles,
    }


def _add_membership(user_id: str, tenant_id: str, role_name: str) -> None:
    from sqlalchemy.orm import Session as DBSession

    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.auth_model import AuthMembershipModel, AuthRoleModel

    db = DBSession(bind=engine)
    try:
        role = db.query(AuthRoleModel).filter(AuthRoleModel.name == role_name).first()
        assert role is not None, f"role {role_name} não existe"
        db.add(
            AuthMembershipModel(
                id=str(uuid.uuid4()),
                user_id=user_id,
                tenant_id=tenant_id,
                role_id=role.id,
            )
        )
        db.commit()
    finally:
        db.close()


def _mk_driver(client, admin: dict, username: str, phone: str) -> dict:
    res = client.post(
        "/admin/drivers",
        headers=admin["headers"],
        json={"name": f"Motorista {username}", "phone": phone, "username": username},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    return {
        "driver_id": body["driver_id"],
        "username": body["username"],
        "temporary_password": body["temporary_password"],
    }


def _list_users(client, headers: dict) -> list:
    res = client.get("/admin/users", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["users"]


# ── Listagem ────────────────────────────────────────────


def test_list_users_scoped_to_own_tenant(client, env):
    users = _list_users(client, env["admin_a"]["headers"])
    ids = {u["id"] for u in users}
    usernames = {u["username"] for u in users}

    # Membros do tenant A visíveis (inclusive o multi-tenant).
    assert env["target_a"]["user_id"] in ids
    assert env["own_a"]["user_id"] in ids
    assert env["multi"]["user_id"] in ids

    # Nada do tenant B vaza — nem users, nem admin, nem credencial de driver.
    assert env["target_b"]["user_id"] not in ids
    assert env["toggle_b"]["user_id"] not in ids
    assert env["admin_b"]["username"] not in usernames
    assert env["driver_b"]["username"] not in usernames

    # E o espelho: B não vê A.
    users_b = _list_users(client, env["admin_b"]["headers"])
    ids_b = {u["id"] for u in users_b}
    assert env["target_b"]["user_id"] in ids_b
    assert env["multi"]["user_id"] in ids_b
    assert env["target_a"]["user_id"] not in ids_b
    assert env["own_a"]["user_id"] not in ids_b


def test_list_users_search_does_not_leak_cross_tenant(client, env):
    """Busca pelo username do usuário alheio devolve vazio (sem oráculo)."""
    res = client.get(
        "/admin/users",
        headers=env["admin_a"]["headers"],
        params={"search": env["target_b"]["username"]},
    )
    assert res.status_code == 200
    assert res.json()["users"] == []

    # Controle positivo: busca pelo próprio alvo do tenant encontra.
    res = client.get(
        "/admin/users",
        headers=env["admin_a"]["headers"],
        params={"search": env["target_a"]["username"]},
    )
    assert res.status_code == 200
    found = res.json()["users"]
    assert [u["id"] for u in found] == [env["target_a"]["user_id"]]


# ── Reset de senha ──────────────────────────────────────


def test_reset_password_cross_tenant_404_and_password_unchanged(client, env):
    """Admin A reseta o usuário de B → 404 e a senha original continua valendo."""
    res = client.post(
        f"/admin/users/{env['target_b']['user_id']}/reset-password",
        headers=env["admin_a"]["headers"],
    )
    assert res.status_code == 404, res.text

    login = client.post(
        "/auth/login",
        json={"username": env["target_b"]["username"], "password": TARGET_PW},
    )
    assert login.status_code == 200, login.text


# ── Edição ──────────────────────────────────────────────


def test_update_user_cross_tenant_404_and_unchanged(client, env):
    res = client.patch(
        f"/admin/users/{env['target_b']['user_id']}",
        headers=env["admin_a"]["headers"],
        json={"display_name": "HACKED PELA EMPRESA A"},
    )
    assert res.status_code == 404, res.text

    users_b = _list_users(client, env["admin_b"]["headers"])
    row = next(u for u in users_b if u["id"] == env["target_b"]["user_id"])
    assert row["display_name"] == "Alvo Empresa B"


# ── Desativação / ativação ──────────────────────────────


def test_deactivate_cross_tenant_404_and_stays_active(client, env):
    res = client.post(
        f"/admin/users/{env['target_b']['user_id']}/deactivate",
        headers=env["admin_a"]["headers"],
    )
    assert res.status_code == 404, res.text

    users_b = _list_users(client, env["admin_b"]["headers"])
    row = next(u for u in users_b if u["id"] == env["target_b"]["user_id"])
    assert row["status"] == "ACTIVE"

    login = client.post(
        "/auth/login",
        json={"username": env["target_b"]["username"], "password": TARGET_PW},
    )
    assert login.status_code == 200, login.text


def test_activate_cross_tenant_404_and_stays_disabled(client, env):
    # Positivo same-tenant primeiro: B desativa o próprio usuário.
    res = client.post(
        f"/admin/users/{env['toggle_b']['user_id']}/deactivate",
        headers=env["admin_b"]["headers"],
    )
    assert res.status_code == 200, res.text

    # Cruzado: A não reativa (nem desativa) usuário alheio → 404, sem efeito.
    res = client.post(
        f"/admin/users/{env['toggle_b']['user_id']}/activate",
        headers=env["admin_a"]["headers"],
    )
    assert res.status_code == 404, res.text
    res = client.post(
        f"/admin/users/{env['toggle_b']['user_id']}/deactivate",
        headers=env["admin_a"]["headers"],
    )
    assert res.status_code == 404, res.text

    users_b = _list_users(client, env["admin_b"]["headers"])
    row = next(u for u in users_b if u["id"] == env["toggle_b"]["user_id"])
    assert row["status"] == "DISABLED"


# ── Fluxos positivos (mesmo tenant continuam funcionando) ──


def test_same_tenant_mutations_still_work(client, env):
    res = client.post(
        f"/admin/users/{env['own_a']['user_id']}/reset-password",
        headers=env["admin_a"]["headers"],
    )
    assert res.status_code == 200, res.text
    temp = res.json()["temporary_password"]
    assert temp

    login = client.post(
        "/auth/login",
        json={"username": env["own_a"]["username"], "password": temp},
    )
    assert login.status_code == 200, login.text

    res = client.patch(
        f"/admin/users/{env['own_a']['user_id']}",
        headers=env["admin_a"]["headers"],
        json={"display_name": "Proprio Renomeado"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["user"]["display_name"] == "Proprio Renomeado"

    res = client.post(
        f"/admin/users/{env['own_a']['user_id']}/deactivate",
        headers=env["admin_a"]["headers"],
    )
    assert res.status_code == 200, res.text
    assert res.json()["user"]["status"] == "DISABLED"

    res = client.post(
        f"/admin/users/{env['own_a']['user_id']}/activate",
        headers=env["admin_a"]["headers"],
    )
    assert res.status_code == 200, res.text
    assert res.json()["user"]["status"] == "ACTIVE"


# ── Usuário multi-tenant ────────────────────────────────


def test_multi_tenant_user_managed_by_both_tenants(client, env):
    """Membro dos dois tenants é editável/resetável pelos dois admins."""
    res = client.patch(
        f"/admin/users/{env['multi']['user_id']}",
        headers=env["admin_b"]["headers"],
        json={"display_name": "Multi Pelo B"},
    )
    assert res.status_code == 200, res.text

    res = client.patch(
        f"/admin/users/{env['multi']['user_id']}",
        headers=env["admin_a"]["headers"],
        json={"display_name": "Multi Pelo A"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["user"]["display_name"] == "Multi Pelo A"

    res = client.post(
        f"/admin/users/{env['multi']['user_id']}/reset-password",
        headers=env["admin_b"]["headers"],
    )
    assert res.status_code == 200, res.text


# ── Papel global não pode ser cunhado por admin de tenant ──


def test_tenant_admin_cannot_assign_global_system_role(client, env):
    system_role_id = env["role_ids"]["SYSTEM"]

    res = client.post(
        "/admin/users",
        headers=env["admin_a"]["headers"],
        json={
            "username": f"mnt_{env['suffix']}",
            "email": f"mnt_{env['suffix']}@gasflow.local",
            "password": TARGET_PW,
            "role": "SYSTEM",
        },
    )
    assert res.status_code == 400, res.text

    res = client.patch(
        f"/admin/users/{env['target_a']['user_id']}",
        headers=env["admin_a"]["headers"],
        json={"role_id": system_role_id},
    )
    assert res.status_code == 400, res.text

    # Papel do alvo permanece OPERATOR (o PATCH abortou antes de mutar).
    users = _list_users(client, env["admin_a"]["headers"])
    row = next(u for u in users if u["id"] == env["target_a"]["user_id"])
    assert row["role_id"] == env["role_ids"]["OPERATOR"]


# ── Credenciais de entregador escopadas pelo tenant ──────


def test_driver_listing_shows_own_tenant_credential_only(client, env):
    """Mesmo `codigo` nos dois tenants: cada admin vê a credencial da sua."""
    res = client.get("/admin/drivers", headers=env["admin_a"]["headers"])
    assert res.status_code == 200, res.text
    drivers_a = res.json()["drivers"]
    row_a = next(d for d in drivers_a if d["driver_id"] == env["driver_a"]["driver_id"])
    assert row_a["username"] == env["driver_a"]["username"]
    assert env["driver_b"]["username"] not in {d["username"] for d in drivers_a}

    res = client.get("/admin/drivers", headers=env["admin_b"]["headers"])
    assert res.status_code == 200, res.text
    drivers_b = res.json()["drivers"]
    row_b = next(d for d in drivers_b if d["driver_id"] == env["driver_b"]["driver_id"])
    assert row_b["username"] == env["driver_b"]["username"]
    assert env["driver_a"]["username"] not in {d["username"] for d in drivers_b}


def test_driver_reset_password_scoped_to_tenant(client, env):
    """Reset por B mexe na credencial de B; a de A permanece intacta."""
    codigo = env["driver_b"]["driver_id"]
    res = client.post(
        f"/admin/drivers/{codigo}/reset-password",
        headers=env["admin_b"]["headers"],
    )
    assert res.status_code == 200, res.text
    temp_new = res.json()["temporary_password"]

    login_b = client.post(
        "/auth/login",
        json={"username": env["driver_b"]["username"], "password": temp_new},
    )
    assert login_b.status_code == 200, login_b.text

    login_a = client.post(
        "/auth/login",
        json={"username": env["driver_a"]["username"], "password": env["driver_a"]["temporary_password"]},
    )
    assert login_a.status_code == 200, login_a.text


def test_driver_reset_cross_tenant_404(client, env):
    """Codigo que só existe em A: reset por B não acha credencial → 404."""
    res = client.post(
        "/admin/drivers",
        headers=env["admin_a"]["headers"],
        json={"name": "Motorista So A", "phone": "11970000002", "username": f"d2a_{env['suffix']}"},
    )
    assert res.status_code == 201, res.text
    codigo_somente_a = res.json()["driver_id"]

    res = client.post(
        f"/admin/drivers/{codigo_somente_a}/reset-password",
        headers=env["admin_b"]["headers"],
    )
    assert res.status_code == 404, res.text


# ── Guards unitários ────────────────────────────────────


def test_actor_and_target_guards_unit(env):
    from sqlalchemy.orm import Session as DBSession

    from app.domain.security.models import SystemRole, TenantContext
    from app.infrastructure.database.init_db import engine
    from app.presentation.api.core.admin import _ensure_actor_in_tenant, _get_tenant_user

    db = DBSession(bind=engine)
    try:
        # Ator sem membership alguma no tenant da sessão → 403.
        stranger = TenantContext(
            user_id=str(uuid.uuid4()),
            tenant_id="sec01_missing_tenant",
            role=SystemRole.OPERATOR,
            permissions={"user.read"},
        )
        with pytest.raises(HTTPException) as exc:
            _ensure_actor_in_tenant(db, stranger)
        assert exc.value.status_code == 403

        actor_a = TenantContext(
            user_id=env["admin_a"]["user_id"],
            tenant_id=env["tenant_a"],
            role=SystemRole.ADMIN,
            permissions=set(),
        )
        # Alvo do próprio tenant carrega.
        loaded = _get_tenant_user(db, actor_a, env["target_a"]["user_id"])
        assert loaded.id == env["target_a"]["user_id"]
        # Alvo de outro tenant → 404 (sem vazar existência).
        with pytest.raises(HTTPException) as exc2:
            _get_tenant_user(db, actor_a, env["target_b"]["user_id"])
        assert exc2.value.status_code == 404
        # Id inexistente → 404.
        with pytest.raises(HTTPException) as exc3:
            _get_tenant_user(db, actor_a, str(uuid.uuid4()))
        assert exc3.value.status_code == 404
        # Multi-tenant passa pelo tenant onde é membro.
        assert _get_tenant_user(db, actor_a, env["multi"]["user_id"]).id == env["multi"]["user_id"]

        # Administrador global (SYSTEM) enxerga qualquer tenant.
        system_ctx = TenantContext(
            user_id=env["system"]["user_id"],
            tenant_id="default",
            role=SystemRole.SYSTEM,
            permissions={"admin.*"},
        )
        assert _ensure_actor_in_tenant(db, system_ctx) is None
        assert _get_tenant_user(db, system_ctx, env["target_b"]["user_id"]).id == env["target_b"]["user_id"]
    finally:
        db.close()


# ── Administrador global preservado ─────────────────────


def test_global_admin_system_role_keeps_cross_tenant_access(client, env):
    """O admin de plataforma (SYSTEM) continua enxergando e operando tudo."""
    users = _list_users(client, env["system"]["headers"])
    ids = {u["id"] for u in users}
    assert env["target_a"]["user_id"] in ids
    assert env["target_b"]["user_id"] in ids

    res = client.post(
        f"/admin/users/{env['target_b']['user_id']}/reset-password",
        headers=env["system"]["headers"],
    )
    assert res.status_code == 200, res.text

    # Credencial de entregador também é alcançável pelo admin global.
    res = client.post(
        f"/admin/drivers/{env['driver_b']['driver_id']}/reset-password",
        headers=env["system"]["headers"],
    )
    assert res.status_code == 200, res.text
