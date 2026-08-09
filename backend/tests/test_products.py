def test_create_product(client):
    resp = client.post(
        "/products/",
        json={"nome": "Água 20L", "tipo": "WATER", "preco": 12.5, "estoque": 40},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == "000001"
    assert data["estoque"] == 40


def test_update_product_partial(client, sample_product):
    codigo = sample_product["codigo"]
    resp = client.put(f"/products/{codigo}", json={"preco": 110.0})
    assert resp.status_code == 200
    assert resp.json()["preco"] == 110.0
    assert resp.json()["nome"] == sample_product["nome"]


def test_disable_product(client, sample_product):
    codigo = sample_product["codigo"]
    client.patch(f"/products/{codigo}/disable")
    assert client.get("/products/").json()["total"] == 0
