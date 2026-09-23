"""CRUD do entregador — editar, excluir e o alias de inativação.

Fecha o que estava quebrado: a tela de edição chamava
`PUT /delivery-drivers/{codigo}`, que não existia (405), e havia dois "excluir"
com efeitos diferentes (`PATCH /delivery-drivers/{codigo}/disable` só derrubava
`ativo`, enquanto `DELETE /admin/drivers/{id}` matava sessão e cadastro).

Decisões cobertas aqui:
- `codigo` é **imutável** (identidade em `delivery_records`/`driver_locations`);
- editar e excluir é **admin-only**;
- excluir é **soft delete** nos dois conceitos (`ativo` = cadastro,
  `status` = operacional) + credencial + sessões + link público;
- entrega em rota bloqueia com **409**.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DBSession

from app.infrastructure.database.init_db import engine
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _driver(client, admin_headers, tag: str):
    """Cria entregador **com credencial** (caminho canônico) e devolve os dados."""
    res = client.post(
        "/admin/drivers",
        headers=admin_headers,
        json={
            "name": f"Entregador {tag}",
            "phone": "91999990000",
            "document": "000.000.000-00",
            "username": f"crud_{tag}_{uuid.uuid4().hex[:6]}",
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


def _row(driver_id: str):
    from app.infrastructure.repositories.delivery_model import DeliveryDriverModel

    db = DBSession(bind=engine)
    try:
        return db.query(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == driver_id).first()
    finally:
        db.close()


def _user_row(driver_id: str):
    from app.infrastructure.repositories.auth_model import AuthUserModel

    db = DBSession(bind=engine)
    try:
        return db.query(AuthUserModel).filter(AuthUserModel.driver_id == driver_id).first()
    finally:
        db.close()


# ── Editar ─────────────────────────────────────────────


def test_put_edita_e_persiste(client, admin_headers):
    driver_id, _ = _driver(client, admin_headers, "edit")

    res = client.put(
        f"/delivery-drivers/{driver_id}",
        headers=admin_headers,
        json={
            "nome": "Nome Editado",
            "telefone": "91912345678",
            "placa": "ABC1D23",
            "document": "11122233344",
            "vehicle_id": "veh-9",
            "status": "PAUSED",
        },
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["nome"] == "Nome Editado"
    assert body["telefone"] == "91912345678"
    assert body["placa"] == "ABC1D23"
    assert body["document"] == "11122233344"
    assert body["vehicle_id"] == "veh-9"
    assert body["status"] == "PAUSED"

    # o GET devolve o mesmo contrato — é o que a tela de edição lê
    got = client.get(f"/delivery-drivers/{driver_id}", headers=admin_headers)
    assert got.status_code == 200, got.text
    assert got.json()["document"] == "11122233344"
    assert got.json()["vehicle_id"] == "veh-9"
    assert got.json()["status"] == "PAUSED"


def test_put_parcial_nao_zera_o_resto(client, admin_headers):
    driver_id, _ = _driver(client, admin_headers, "parcial")
    antes = client.get(f"/delivery-drivers/{driver_id}", headers=admin_headers).json()

    res = client.put(f"/delivery-drivers/{driver_id}", headers=admin_headers, json={"placa": "XYZ9Z99"})

    assert res.status_code == 200, res.text
    assert res.json()["placa"] == "XYZ9Z99"
    assert res.json()["nome"] == antes["nome"]
    assert res.json()["telefone"] == antes["telefone"]


def test_codigo_e_imutavel(client, admin_headers):
    """`codigo` no corpo → 422, em vez de ignorar em silêncio."""
    driver_id, _ = _driver(client, admin_headers, "imut")
    antes = client.get(f"/delivery-drivers/{driver_id}", headers=admin_headers).json()

    res = client.put(
        f"/delivery-drivers/{driver_id}",
        headers=admin_headers,
        json={"nome": "Tentativa", "codigo": "999999"},
    )

    assert res.status_code == 422, res.text
    depois = client.get(f"/delivery-drivers/{driver_id}", headers=admin_headers).json()
    assert depois["nome"] == antes["nome"]
    assert depois["codigo"] == driver_id


@pytest.mark.parametrize("campo", ["nome", "telefone"])
def test_put_rejeita_campo_vazio(client, admin_headers, campo):
    driver_id, _ = _driver(client, admin_headers, f"vazio{campo[:2]}")

    res = client.put(f"/delivery-drivers/{driver_id}", headers=admin_headers, json={campo: ""})

    assert res.status_code == 422, res.text


def test_put_de_outro_tenant_da_404(client, admin_headers):
    """Entregador de outro tenant → 404 (403 vazaria a existência)."""
    from app.infrastructure.repositories.delivery_model import DeliveryDriverModel

    codigo = f"9{uuid.uuid4().hex[:5]}"
    db = DBSession(bind=engine)
    try:
        db.add(DeliveryDriverModel(tenant_id="outro-tenant", codigo=codigo, nome="De Outro", telefone="91000000000"))
        db.commit()
    finally:
        db.close()

    res = client.put(f"/delivery-drivers/{codigo}", headers=admin_headers, json={"nome": "Invasor"})

    assert res.status_code == 404, res.text


def test_put_inexistente_da_404(client, admin_headers):
    res = client.put("/delivery-drivers/nao-existe", headers=admin_headers, json={"nome": "X"})
    assert res.status_code == 404, res.text


def test_put_exige_admin(client, admin_headers):
    """Operador (não-admin) não edita cadastro de entregador."""
    driver_id, _ = _driver(client, admin_headers, "perm")
    username = f"oper_{uuid.uuid4().hex[:6]}"
    created = client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": username,
            "email": f"{username}@gasflow.test",
            "password": "SenhaForte123",
            "display_name": "Operador CRUD",
            "role": "OPERATOR",
        },
    )
    assert created.status_code in (200, 201), created.text

    login = client.post("/auth/login", json={"username": username, "password": "SenhaForte123"})
    assert login.status_code == 200, login.text
    oper_headers = {"Authorization": f"Bearer {login.json()['token']}"}

    res = client.put(f"/delivery-drivers/{driver_id}", headers=oper_headers, json={"nome": "Operador Tentou"})

    assert res.status_code == 403, res.text


# ── Excluir ────────────────────────────────────────────


def test_excluir_desativa_cadastro_credencial_e_rastreio(client, admin_headers):
    driver_id, driver_headers = _driver(client, admin_headers, "del")
    epoch_antes = int(_row(driver_id).tracking_epoch or 0)

    # o entregador logado funciona antes
    assert client.get("/driver/me", headers=driver_headers).status_code == 200

    res = client.delete(f"/admin/drivers/{driver_id}", headers=admin_headers)

    assert res.status_code == 200, res.text
    assert res.json()["success"] is True
    assert res.json()["driver_id"] == driver_id

    row = _row(driver_id)
    assert row.ativo is False
    assert row.status == "DISABLED"
    assert int(row.tracking_epoch or 0) > epoch_antes, "o epoch precisa avançar (mata link público já emitido)"

    user = _user_row(driver_id)
    assert user is not None and user.status == "DISABLED"

    # sessão revogada: o token que funcionava não vale mais
    depois = client.get("/driver/me", headers=driver_headers)
    assert depois.status_code in (401, 403), depois.text


def test_excluir_bloqueia_entrega_em_rota(client, admin_headers):
    driver_id, _ = _driver(client, admin_headers, "rota")

    created = client.post(
        "/delivery/deliveries",
        headers=admin_headers,
        json={
            "order_id": f"ord_{uuid.uuid4().hex[:10]}",
            "customer_codigo": f"cli_{uuid.uuid4().hex[:6]}",
            "customer_name": "Cliente Rota",
            "notes": "entrega em rota",
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

    res = client.delete(f"/admin/drivers/{driver_id}", headers=admin_headers)

    assert res.status_code == 409, res.text
    row = _row(driver_id)
    assert row.ativo is True, "bloqueado não pode desativar o cadastro"
    assert row.status != "DISABLED"


def test_excluir_inexistente_da_404(client, admin_headers):
    res = client.delete("/admin/drivers/nao-existe", headers=admin_headers)
    assert res.status_code == 404, res.text


def test_disable_e_alias_com_o_mesmo_efeito(client, admin_headers):
    """`PATCH .../disable` precisa ter o mesmo efeito do delete, não um menor."""
    driver_id, driver_headers = _driver(client, admin_headers, "alias")
    epoch_antes = int(_row(driver_id).tracking_epoch or 0)

    res = client.patch(f"/delivery-drivers/{driver_id}/disable", headers=admin_headers)

    assert res.status_code == 200, res.text
    row = _row(driver_id)
    assert row.ativo is False
    assert row.status == "DISABLED"
    assert int(row.tracking_epoch or 0) > epoch_antes

    user = _user_row(driver_id)
    assert user is not None and user.status == "DISABLED"
    assert client.get("/driver/me", headers=driver_headers).status_code in (401, 403)
