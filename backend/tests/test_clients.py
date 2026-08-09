def test_create_and_get_client(client):
    resp = client.post(
        "/clients/",
        json={
            "nome": "João",
            "telefone": "11988887777",
            "rua": "Rua A",
            "numero": "100",
            "bairro": "Jardim",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == "000001"
    assert data["ativo"] is True

    got = client.get(f"/clients/{data['codigo']}")
    assert got.status_code == 200
    assert got.json()["nome"] == "João"


def test_client_code_increments(client):
    c1 = client.post(
        "/clients/",
        json={"nome": "A", "telefone": "1", "rua": "R", "numero": "1", "bairro": "B"},
    ).json()
    c2 = client.post(
        "/clients/",
        json={"nome": "B", "telefone": "2", "rua": "R", "numero": "2", "bairro": "B"},
    ).json()
    assert c1["codigo"] == "000001"
    assert c2["codigo"] == "000002"


def test_list_clients_is_paginated(client, sample_client):
    resp = client.get("/clients/?limit=10&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["limit"] == 10
    assert len(body["items"]) == 1


def test_get_missing_client_returns_404(client):
    assert client.get("/clients/999999").status_code == 404


def test_disable_client_hides_from_list(client, sample_client):
    codigo = sample_client["codigo"]
    client.patch(f"/clients/{codigo}/disable")
    assert client.get("/clients/").json()["total"] == 0
