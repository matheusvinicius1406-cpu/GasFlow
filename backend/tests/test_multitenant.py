"""Testa o isolamento multi-tenant: cada empresa só enxerga os próprios dados."""


def _company(client, nome):
    return client.post("/companies/", json={"nome": nome}).json()


def _headers(company):
    return {"X-Company-Id": company["codigo"]}


def test_create_company_generates_code(client):
    a = _company(client, "Depósito A")
    b = _company(client, "Depósito B")
    assert a["codigo"] == "000001"
    assert b["codigo"] == "000002"


def test_clients_are_isolated_by_company(client):
    a = _company(client, "Depósito A")
    b = _company(client, "Depósito B")

    client.post(
        "/clients/",
        headers=_headers(a),
        json={"nome": "Cliente A", "telefone": "1", "rua": "R", "numero": "1", "bairro": "B"},
    )
    client.post(
        "/clients/",
        headers=_headers(b),
        json={"nome": "Cliente B", "telefone": "2", "rua": "R", "numero": "2", "bairro": "B"},
    )

    list_a = client.get("/clients/", headers=_headers(a)).json()
    list_b = client.get("/clients/", headers=_headers(b)).json()

    assert list_a["total"] == 1
    assert list_b["total"] == 1
    assert list_a["items"][0]["nome"] == "Cliente A"
    assert list_b["items"][0]["nome"] == "Cliente B"


def test_codes_restart_per_company(client):
    a = _company(client, "Depósito A")
    b = _company(client, "Depósito B")

    ca = client.post(
        "/clients/",
        headers=_headers(a),
        json={"nome": "A1", "telefone": "1", "rua": "R", "numero": "1", "bairro": "B"},
    ).json()
    cb = client.post(
        "/clients/",
        headers=_headers(b),
        json={"nome": "B1", "telefone": "2", "rua": "R", "numero": "2", "bairro": "B"},
    ).json()

    # Cada empresa tem sua própria numeração começando em 000001.
    assert ca["codigo"] == "000001"
    assert cb["codigo"] == "000001"


def test_cannot_read_other_company_client(client):
    a = _company(client, "Depósito A")
    b = _company(client, "Depósito B")

    ca = client.post(
        "/clients/",
        headers=_headers(a),
        json={"nome": "A1", "telefone": "1", "rua": "R", "numero": "1", "bairro": "B"},
    ).json()

    # Empresa B tenta ler o cliente da empresa A pelo código -> 404.
    resp = client.get(f"/clients/{ca['codigo']}", headers=_headers(b))
    assert resp.status_code == 404


def test_order_cannot_use_other_company_product(client):
    a = _company(client, "Depósito A")
    b = _company(client, "Depósito B")

    # Produto pertence à empresa A.
    prod_a = client.post(
        "/products/",
        headers=_headers(a),
        json={"nome": "Gás", "tipo": "GAS", "preco": 100.0, "estoque": 10},
    ).json()
    # Cliente pertence à empresa B.
    cli_b = client.post(
        "/clients/",
        headers=_headers(b),
        json={"nome": "B1", "telefone": "2", "rua": "R", "numero": "2", "bairro": "B"},
    ).json()

    # Empresa B tenta criar pedido com produto da empresa A -> produto não encontrado.
    resp = client.post(
        "/orders/",
        headers=_headers(b),
        json={"client_codigo": cli_b["codigo"], "product": prod_a["codigo"], "quantity": 1},
    )
    assert resp.status_code == 404


def test_unknown_company_header_returns_404(client):
    resp = client.get("/clients/", headers={"X-Company-Id": "999999"})
    assert resp.status_code == 404


def test_default_company_used_without_header(client):
    # Sem header, opera na empresa padrão; deve funcionar normalmente.
    resp = client.post(
        "/clients/",
        json={"nome": "Sem header", "telefone": "9", "rua": "R", "numero": "9", "bairro": "B"},
    )
    assert resp.status_code == 200
    assert client.get("/clients/").json()["total"] == 1
