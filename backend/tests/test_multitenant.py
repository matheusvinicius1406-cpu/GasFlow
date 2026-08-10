"""Isolamento multi-tenant: cada empresa só enxerga os próprios dados.

Com autenticação (Fase 2), o tenant vem do token do usuário, não de um header.
"""

from tests.conftest import bearer, register_company

CLIENT_A = {"nome": "Cliente A", "telefone": "1", "rua": "R", "numero": "1", "bairro": "B"}
CLIENT_B = {"nome": "Cliente B", "telefone": "2", "rua": "R", "numero": "2", "bairro": "B"}


def _two_companies(raw_client):
    token_a = register_company(raw_client, "Depósito A", "a@test.com")
    token_b = register_company(raw_client, "Depósito B", "b@test.com")
    return token_a, token_b


def test_clients_are_isolated_by_company(raw_client):
    token_a, token_b = _two_companies(raw_client)

    raw_client.post("/clients/", headers=bearer(token_a), json=CLIENT_A)
    raw_client.post("/clients/", headers=bearer(token_b), json=CLIENT_B)

    list_a = raw_client.get("/clients/", headers=bearer(token_a)).json()
    list_b = raw_client.get("/clients/", headers=bearer(token_b)).json()

    assert list_a["total"] == 1
    assert list_b["total"] == 1
    assert list_a["items"][0]["nome"] == "Cliente A"
    assert list_b["items"][0]["nome"] == "Cliente B"


def test_codes_restart_per_company(raw_client):
    token_a, token_b = _two_companies(raw_client)

    ca = raw_client.post("/clients/", headers=bearer(token_a), json=CLIENT_A).json()
    cb = raw_client.post("/clients/", headers=bearer(token_b), json=CLIENT_B).json()

    # Cada empresa tem sua própria numeração começando em 000001.
    assert ca["codigo"] == "000001"
    assert cb["codigo"] == "000001"


def test_cannot_read_other_company_client(raw_client):
    token_a, token_b = _two_companies(raw_client)

    ca = raw_client.post("/clients/", headers=bearer(token_a), json=CLIENT_A).json()

    # Empresa B tenta ler o cliente da empresa A pelo código -> 404.
    resp = raw_client.get(f"/clients/{ca['codigo']}", headers=bearer(token_b))
    assert resp.status_code == 404


def test_order_cannot_use_other_company_product(raw_client):
    token_a, token_b = _two_companies(raw_client)

    prod_a = raw_client.post(
        "/products/",
        headers=bearer(token_a),
        json={"nome": "Gás", "tipo": "GAS", "preco": 100.0, "estoque": 10},
    ).json()
    cli_b = raw_client.post("/clients/", headers=bearer(token_b), json=CLIENT_B).json()

    # Empresa B tenta criar pedido com produto da empresa A -> produto não encontrado.
    resp = raw_client.post(
        "/orders/",
        headers=bearer(token_b),
        json={"client_codigo": cli_b["codigo"], "product": prod_a["codigo"], "quantity": 1},
    )
    assert resp.status_code == 404


def test_companies_me_returns_own_company(raw_client):
    token_a, token_b = _two_companies(raw_client)
    a = raw_client.get("/companies/me", headers=bearer(token_a)).json()
    b = raw_client.get("/companies/me", headers=bearer(token_b)).json()
    assert a["nome"] == "Depósito A"
    assert b["nome"] == "Depósito B"
