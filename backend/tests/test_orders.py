def _create_order(client, client_codigo, product_codigo, quantity=1, payment="PIX"):
    return client.post(
        "/orders/",
        json={
            "client_codigo": client_codigo,
            "items": [{"product": product_codigo, "quantity": quantity}],
            "payment_method": payment,
        },
    )


def test_create_order_decrements_stock(client, sample_client, sample_product):
    resp = _create_order(client, sample_client["codigo"], sample_product["codigo"], 3)
    assert resp.status_code == 200
    order = resp.json()
    assert order["value"] == 300.0
    assert order["status"] == "PENDING"
    assert len(order["items"]) == 1
    assert order["items"][0]["subtotal"] == 300.0

    product = client.get(f"/products/{sample_product['codigo']}").json()
    assert product["estoque"] == 7  # 10 - 3


def test_create_multi_item_order(client, sample_client, sample_product):
    p2 = client.post(
        "/products/",
        json={"nome": "Água 20L", "tipo": "WATER", "preco": 10.0, "estoque": 20},
    ).json()

    resp = client.post(
        "/orders/",
        json={
            "client_codigo": sample_client["codigo"],
            "items": [
                {"product": sample_product["codigo"], "quantity": 2},
                {"product": p2["codigo"], "quantity": 5},
            ],
        },
    )
    assert resp.status_code == 200
    order = resp.json()
    assert order["value"] == 2 * 100.0 + 5 * 10.0
    assert len(order["items"]) == 2


def test_order_insufficient_stock_returns_422(client, sample_client, sample_product):
    resp = _create_order(client, sample_client["codigo"], sample_product["codigo"], 999)
    assert resp.status_code == 422
    assert "insuficiente" in resp.json()["detail"].lower()


def test_order_missing_client_returns_404(client, sample_product):
    resp = _create_order(client, "999999", sample_product["codigo"], 1)
    assert resp.status_code == 404


def test_order_missing_product_returns_404(client, sample_client):
    resp = _create_order(client, sample_client["codigo"], "999999", 1)
    assert resp.status_code == 404


def test_valid_status_transition(client, sample_client, sample_product):
    order = _create_order(client, sample_client["codigo"], sample_product["codigo"], 1).json()
    resp = client.patch(f"/orders/{order['codigo']}/status", json={"status": "CONFIRMED"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "CONFIRMED"


def test_invalid_status_transition_returns_422(client, sample_client, sample_product):
    order = _create_order(client, sample_client["codigo"], sample_product["codigo"], 1).json()
    # PENDING -> DELIVERED não é permitido (deve passar pelos estados intermediários).
    resp = client.patch(f"/orders/{order['codigo']}/status", json={"status": "DELIVERED"})
    assert resp.status_code == 422
    assert "inválida" in resp.json()["detail"].lower()


def test_cancel_restocks_inventory(client, sample_client, sample_product):
    order = _create_order(client, sample_client["codigo"], sample_product["codigo"], 4).json()
    assert client.get(f"/products/{sample_product['codigo']}").json()["estoque"] == 6

    resp = client.patch(f"/orders/{order['codigo']}/status", json={"status": "CANCELLED"})
    assert resp.status_code == 200
    # Estoque devolvido ao cancelar.
    assert client.get(f"/products/{sample_product['codigo']}").json()["estoque"] == 10


def test_order_history_records_transitions(client, sample_client, sample_product):
    order = _create_order(client, sample_client["codigo"], sample_product["codigo"], 1).json()
    client.patch(f"/orders/{order['codigo']}/status", json={"status": "CONFIRMED"})

    history = client.get(f"/orders/{order['codigo']}/history").json()
    assert len(history) == 2
    assert history[0]["from_status"] is None
    assert history[0]["to_status"] == "PENDING"
    assert history[1]["from_status"] == "PENDING"
    assert history[1]["to_status"] == "CONFIRMED"


def test_assign_driver(client, sample_client, sample_product):
    order = _create_order(client, sample_client["codigo"], sample_product["codigo"], 1).json()
    driver = client.post(
        "/delivery-drivers/",
        json={"nome": "Carlos", "telefone": "11955554444", "placa": "ABC1234"},
    ).json()
    resp = client.patch(
        f"/orders/{order['codigo']}/assign-driver",
        json={"delivery_driver_codigo": driver["codigo"]},
    )
    assert resp.status_code == 200
    assert resp.json()["delivery_driver_codigo"] == driver["codigo"]


def test_list_orders_filter_by_status(client, sample_client, sample_product):
    _create_order(client, sample_client["codigo"], sample_product["codigo"], 1)
    assert client.get("/orders/").json()["total"] == 1
    assert client.get("/orders/?status=CANCELLED").json()["total"] == 0
