"""Autenticação e RBAC."""

from tests.conftest import bearer, register_company

CLIENT = {"nome": "C", "telefone": "1", "rua": "R", "numero": "1", "bairro": "B"}
PRODUCT = {"nome": "Gás", "tipo": "GAS", "preco": 100.0, "estoque": 10}


def test_register_returns_tokens(raw_client):
    resp = raw_client.post(
        "/auth/register",
        json={
            "empresa_nome": "Depósito X",
            "nome": "Dono",
            "email": "dono@x.com",
            "senha": "senha123",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_register_duplicate_email_conflicts(raw_client):
    register_company(raw_client, "Dep 1", "dup@test.com")
    resp = raw_client.post(
        "/auth/register",
        json={
            "empresa_nome": "Dep 2",
            "nome": "Outro",
            "email": "dup@test.com",
            "senha": "senha123",
        },
    )
    assert resp.status_code == 409


def test_login_and_me(raw_client):
    register_company(raw_client, "Dep", "user@test.com", senha="segredo123", nome="Fulano")
    resp = raw_client.post("/auth/login", json={"email": "user@test.com", "senha": "segredo123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    me = raw_client.get("/auth/me", headers=bearer(token)).json()
    assert me["email"] == "user@test.com"
    assert me["role"] == "OWNER"


def test_login_wrong_password_401(raw_client):
    register_company(raw_client, "Dep", "user@test.com", senha="certa123")
    resp = raw_client.post("/auth/login", json={"email": "user@test.com", "senha": "errada"})
    assert resp.status_code == 401


def test_refresh_token(raw_client):
    resp = raw_client.post(
        "/auth/register",
        json={
            "empresa_nome": "Dep",
            "nome": "Dono",
            "email": "r@test.com",
            "senha": "senha123",
        },
    ).json()
    new = raw_client.post("/auth/refresh", json={"refresh_token": resp["refresh_token"]})
    assert new.status_code == 200
    assert new.json()["access_token"]


def test_protected_endpoint_requires_auth(raw_client):
    assert raw_client.get("/clients/").status_code == 401


def test_invalid_token_401(raw_client):
    assert raw_client.get("/clients/", headers=bearer("garbage")).status_code == 401


def _attendant_token(raw_client, client):
    """Cria um ATTENDANT na empresa do `client` (OWNER) e devolve seu token."""
    client.post(
        "/users/",
        json={"nome": "Atend", "email": "atend@test.com", "senha": "senha123", "role": "ATTENDANT"},
    )
    resp = raw_client.post("/auth/login", json={"email": "atend@test.com", "senha": "senha123"})
    return resp.json()["access_token"]


def test_attendant_cannot_create_product(raw_client, client):
    token = _attendant_token(raw_client, client)
    resp = raw_client.post("/products/", headers=bearer(token), json=PRODUCT)
    assert resp.status_code == 403


def test_attendant_can_create_client(raw_client, client):
    token = _attendant_token(raw_client, client)
    resp = raw_client.post("/clients/", headers=bearer(token), json=CLIENT)
    assert resp.status_code == 200


def test_attendant_cannot_manage_users(raw_client, client):
    token = _attendant_token(raw_client, client)
    resp = raw_client.post(
        "/users/",
        headers=bearer(token),
        json={"nome": "Novo", "email": "novo@test.com", "senha": "senha123", "role": "DRIVER"},
    )
    assert resp.status_code == 403


def test_owner_can_create_and_list_users(client):
    created = client.post(
        "/users/",
        json={"nome": "Adm", "email": "adm@test.com", "senha": "senha123", "role": "ADMIN"},
    )
    assert created.status_code == 200
    listing = client.get("/users/").json()
    # OWNER (auto) + ADMIN criado = 2
    assert listing["total"] == 2
