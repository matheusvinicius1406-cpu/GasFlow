def _create_order(client, client_codigo, product_codigo, quantity=1):
    return client.post(
        "/orders/",
        json={
            "client_codigo": client_codigo,
            "product": product_codigo,
            "quantity": quantity,
            "payment_method": "PIX",
        },
    )


def test_create_order_decrements_stock(client, sample_client, sample_product):
    resp = _create_order(client, sample_client["codigo"], sample_product["codigo"], 3)
    assert resp.status_code == 200
    order = resp.json()
    assert order["value"] == 300.0
    assert order["status"] == "PENDING"

    product = client.get(f"/products/{sample_product['codigo']}").json()
    assert product["estoque"] == 7  # 10 - 3


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


def test_update_order_status(client, sample_client, sample_product):
    order = _create_order(client, sample_client["codigo"], sample_product["codigo"], 1).json()
    resp = client.patch(f"/orders/{order['codigo']}/status", json={"status": "CONFIRMED"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "CONFIRMED"


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
    all_orders = client.get("/orders/").json()
    assert all_orders["total"] == 1
    cancelled = client.get("/orders/?status=CANCELLED").json()
    assert cancelled["total"] == 0
