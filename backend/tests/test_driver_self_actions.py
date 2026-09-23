"""Ações de entrega no namespace do app (`/driver/*`) com a auth principal.

Regressão do buraco que quebrava o app do entregador: ele loga em
`/auth/login` (auth principal, `role=DRIVER`) e as ações existiam só em
`/api/v1/driver/*` (`driver_v1` → `_authenticate_driver`), que aceita **sessão
de driver no banco** ou **JWT de escopo `mobile`**. O token que o app tem não
passa por nenhum dos dois → 401 em aceitar/iniciar/concluir/falhar.

Cobre:
- as ações autenticam com o token principal do entregador e mudam o estado
- admin (não-driver) → 403
- entregador não age na entrega de outro → 404
- `POST /driver/location` (alias principal do ingest legado) responde 200
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        # Janela LGPD ampla: o ingest de posição não depende do relógio da máquina.
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


def _active_driver(client, admin_headers, tag: str):
    """Cria entregador, troca a senha e devolve (driver_id, headers da auth principal)."""
    res = client.post(
        "/admin/drivers",
        headers=admin_headers,
        json={
            "name": f"Entregador {tag}",
            "phone": "91999990000",
            "document": "111.111.111-11",
            "username": f"act_{tag}_{uuid.uuid4().hex[:6]}",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()

    login = client.post(
        "/auth/login",
        json={"username": body["username"], "password": body["temporary_password"]},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['token']}"}

    changed = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": body["temporary_password"], "new_password": "NovaSenha123"},
    )
    assert changed.status_code == 200, changed.text
    return body["driver_id"], headers


def _assigned_delivery(client, admin_headers, driver_id: str) -> str:
    """Cria uma entrega e atribui ao entregador; devolve o delivery_id."""
    created = client.post(
        "/delivery/deliveries",
        headers=admin_headers,
        json={
            "order_id": f"ord_{uuid.uuid4().hex[:10]}",
            "customer_codigo": f"cli_{uuid.uuid4().hex[:6]}",
            "customer_name": "Cliente Ações",
            "notes": "teste de ações",
        },
    )
    assert created.status_code == 200, created.text
    delivery_id = created.json()["delivery"]["id"]

    assigned = client.patch(
        f"/delivery/deliveries/{delivery_id}/assign",
        headers=admin_headers,
        json={"driver_id": driver_id},
    )
    assert assigned.status_code == 200, assigned.text
    return delivery_id


# ── Autorização ──────────────────────────────────────────


def test_admin_nao_usa_acao_do_entregador(client, admin_headers):
    delivery_id = _assigned_delivery(client, admin_headers, _active_driver(client, admin_headers, "a")[0])
    res = client.post(f"/driver/deliveries/{delivery_id}/start", headers=admin_headers, json={})
    assert res.status_code == 403, res.text


def test_sem_token_da_401(client):
    res = client.post("/driver/deliveries/qualquer/start", json={})
    assert res.status_code == 401, res.text


# ── Ações com a auth principal ───────────────────────────


def test_entregador_inicia_entrega_com_token_principal(client, admin_headers):
    """O token do `/auth/login` precisa bastar — era exatamente o que faltava."""
    driver_id, driver_headers = _active_driver(client, admin_headers, "b")
    delivery_id = _assigned_delivery(client, admin_headers, driver_id)

    res = client.post(f"/driver/deliveries/{delivery_id}/start", headers=driver_headers, json={})

    assert res.status_code == 200, res.text
    assert res.json()["success"] is True


def test_entregador_nao_age_na_entrega_de_outro(client, admin_headers):
    dono_id, _ = _active_driver(client, admin_headers, "c")
    _, intruso_headers = _active_driver(client, admin_headers, "d")
    delivery_id = _assigned_delivery(client, admin_headers, dono_id)

    res = client.post(f"/driver/deliveries/{delivery_id}/start", headers=intruso_headers, json={})

    assert res.status_code == 404, res.text


def test_entrega_inexistente_da_404(client, admin_headers):
    _, driver_headers = _active_driver(client, admin_headers, "e")
    res = client.post("/driver/deliveries/nao-existe/start", headers=driver_headers, json={})
    assert res.status_code == 404, res.text


# ── Posição ─────────────────────────────────────────────


def test_location_alias_aceita_token_principal(client, admin_headers):
    _, driver_headers = _active_driver(client, admin_headers, "f")

    res = client.post(
        "/driver/location",
        headers=driver_headers,
        json={"latitude": -23.55, "longitude": -46.63},
    )

    assert res.status_code == 200, res.text
    assert res.json()["success"] is True


def test_location_alias_exige_driver(client, admin_headers):
    res = client.post(
        "/driver/location",
        headers=admin_headers,
        json={"latitude": -23.55, "longitude": -46.63},
    )
    assert res.status_code == 403, res.text


# ── Ciclo do painel (estava em 500 pelo mesmo motivo) ────


def test_status_terminal_libera_o_entregador(client, admin_headers):
    """`PATCH /delivery/deliveries/{id}/status` chamava `set_available()` na
    entidade desconectada — 500 depois de já ter persistido a mudança."""
    driver_id, _ = _active_driver(client, admin_headers, "g")
    delivery_id = _assigned_delivery(client, admin_headers, driver_id)

    res = client.patch(
        f"/delivery/deliveries/{delivery_id}/status",
        headers=admin_headers,
        json={"status": "CANCELLED"},
    )
    assert res.status_code == 200, res.text

    snap = client.get(f"/delivery/drivers/{driver_id}", headers=admin_headers)
    assert snap.status_code == 200, snap.text
    assert snap.json()["driver"]["status"] == "AVAILABLE"


def test_criar_entregador_pelo_delivery_ops(client, admin_headers):
    """`POST /delivery/drivers` é alias do cadastro canônico.

    Dois consertos nesta rota: antes ela montava um `DriverDomain` (campos
    `name`/`phone`, sem `codigo`) e passava para o repositório que lê a entidade
    de `domain/delivery/entity.py` — AttributeError em toda criação. Depois
    passou a criar **só a entidade**, sem credencial: o entregador cadastrado
    aqui não conseguia abrir o app. Agora devolve a senha temporária e o login
    funciona.
    """
    nome = f"Entregador {uuid.uuid4().hex[:6]}"
    res = client.post(
        "/delivery/drivers",
        headers=admin_headers,
        json={
            "name": nome,
            "phone": "91988887777",
            "license_number": "12345678900",
            "vehicle_id": "veh-teste",
        },
    )

    assert res.status_code == 201, res.text
    body = res.json()
    assert len(body["driver_id"]) == 6
    assert body["username"] == f"drv_{body['driver_id']}"
    assert body["temporary_password"]

    # `license_number`/`vehicle_id` não podem sumir no caminho.
    driver_id = body["driver_id"]
    got = client.get(f"/delivery/drivers/{driver_id}", headers=admin_headers)
    assert got.status_code == 200, got.text
    snapshot = got.json()["driver"]
    assert snapshot["nome"] == nome
    assert snapshot["status"] == "AVAILABLE"
    assert snapshot["document"] == "12345678900"
    assert snapshot["vehicle_id"] == "veh-teste"

    # A credencial existe de verdade: loga e passa pelo gate de troca de senha.
    login = client.post(
        "/auth/login",
        json={"username": body["username"], "password": body["temporary_password"]},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    changed = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": body["temporary_password"], "new_password": "NovaSenha123"},
    )
    assert changed.status_code == 200, changed.text
    me = client.get("/driver/me", headers=headers)
    assert me.status_code == 200, me.text


def test_alias_e_canonico_produzem_o_mesmo_efeito(client, admin_headers):
    """Os dois entrypoints de criação têm de criar as MESMAS linhas.

    Antes divergiam: o canônico criava entidade + credencial, o alias só a
    entidade. É essa comparação que impede a divergência de voltar.
    """
    from sqlalchemy.orm import Session as DBSession

    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.auth_model import AuthMembershipModel, AuthUserModel
    from app.infrastructure.repositories.delivery_model import DeliveryDriverModel

    def _criar(path, payload):
        res = client.post(path, headers=admin_headers, json=payload)
        assert res.status_code == 201, res.text
        return res.json()

    canonico = _criar("/admin/drivers", {"name": "Canônico", "phone": "91990000001"})
    alias = _criar("/delivery/drivers", {"name": "Alias", "phone": "91990000002"})

    db = DBSession(bind=engine)
    try:
        for criado, nome in ((canonico, "Canônico"), (alias, "Alias")):
            codigo = criado["driver_id"]
            driver = db.query(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == codigo).first()
            assert driver is not None and driver.nome == nome
            assert driver.ativo is True and driver.status == "AVAILABLE"

            user = db.query(AuthUserModel).filter(AuthUserModel.driver_id == codigo).first()
            assert user is not None, "o alias não criou credencial"
            assert user.username == criado["username"]
            assert user.status == "ACTIVE"
            assert user.must_change_password is True

            membership = db.query(AuthMembershipModel).filter(AuthMembershipModel.user_id == user.id).first()
            assert membership is not None, "sem membership o login cairia em OPERATOR"
            assert membership.tenant_id == driver.tenant_id
    finally:
        db.close()

    # e os dois conseguem logar com a senha devolvida
    for criado in (canonico, alias):
        login = client.post(
            "/auth/login",
            json={"username": criado["username"], "password": criado["temporary_password"]},
        )
        assert login.status_code == 200, login.text


def test_auditoria_registra_uma_vez_por_criacao(client, admin_headers):
    """A criação passou para a camada de aplicação — o audit não pode duplicar."""
    res = client.post(
        "/delivery/drivers",
        headers=admin_headers,
        json={"name": "Auditado", "phone": "91990000003"},
    )
    assert res.status_code == 201, res.text
    codigo = res.json()["driver_id"]

    records = client.get(
        "/admin/audit",
        headers=admin_headers,
        params={"action": "USER_CREATED", "resource": "driver"},
    ).json()["records"]
    do_driver = [r for r in records if r["resource_id"] == codigo]
    assert len(do_driver) == 1, do_driver
    # a senha temporária nunca entra no audit
    assert res.json()["temporary_password"] not in str(do_driver)
    assert do_driver[0]["after_json"]["username"] == res.json()["username"]


def test_status_do_entregador_persiste(client, admin_headers):
    driver_id, _ = _active_driver(client, admin_headers, "h")

    res = client.patch(
        f"/delivery/drivers/{driver_id}/status",
        headers=admin_headers,
        params={"status": "PAUSED"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["driver"]["status"] == "PAUSED"

    snap = client.get(f"/delivery/drivers/{driver_id}", headers=admin_headers)
    assert snap.json()["driver"]["status"] == "PAUSED"
