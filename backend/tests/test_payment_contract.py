"""
Payment Contract Tests — Bloco A

Validates:
- P1-01: PaymentCreate contract (order_codigo from path, not body)
- P1-02: order.payment_status sync (PARTIAL, PAID)
- P2-02: Idempotency (same key → same payment, different key → different payment)
- Overpayment rejection
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    resp = client.post(
        "/auth/login",
        json={
            "username": "admin",
            "password": "test_password_123",
        },
    )
    assert resp.status_code == 200
    return resp.json()["token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


_counter = 0


def _unique():
    global _counter
    _counter += 1
    return _counter


def _create_receivable(client, headers, order_codigo, customer_codigo, total):
    """Create a receivable for an order via the use case (no API endpoint)."""
    from app.infrastructure.repositories.financial_repositories import (
        SQLAlchemyReceivableRepository,
        SQLAlchemyFinancialLedgerRepository,
    )
    from app.application.financial.use_cases import CreateReceivableUseCase
    from decimal import Decimal

    # Use the same DB and tenant as the test client
    from app.infrastructure.database.init_db import engine
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        uc = CreateReceivableUseCase(
            receivable_repo=SQLAlchemyReceivableRepository(db, "default"),
            ledger_repo=SQLAlchemyFinancialLedgerRepository(db, "default"),
        )
        uc.execute(order_codigo, customer_codigo, Decimal(str(total)))


def _create_order(client, headers, name_suffix="", total=100.00):
    """Helper: create client + product + stock + order + receivable. Returns order_codigo."""
    n = _unique()

    client_resp = client.post(
        "/clients/",
        json={
            "nome": f"PayTest Client {n} {name_suffix}",
            "telefone": f"119999{n:06d}",
            "rua": "Rua Teste",
            "numero": str(n),
            "bairro": "Centro",
        },
        headers=headers,
    )
    assert client_resp.status_code == 200, f"Client: {client_resp.json()}"
    client_codigo = client_resp.json()["codigo"]

    prod_resp = client.post(
        "/products/",
        json={
            "nome": f"PayTest Product {n} {name_suffix}",
            "preco": total,
            "tipo": "GAS",
        },
        headers=headers,
    )
    assert prod_resp.status_code == 200, f"Product: {prod_resp.json()}"
    product_codigo = prod_resp.json()["codigo"]

    # Add stock
    stock_resp = client.post(
        f"/inventory/{product_codigo}/entries",
        json={"quantity": 100},
        headers=headers,
    )
    assert stock_resp.status_code == 200, f"Stock: {stock_resp.json()}"

    order_resp = client.post(
        "/orders/",
        json={
            "client_codigo": client_codigo,
            "items": [{"product_codigo": product_codigo, "quantity": 1}],
        },
        headers=headers,
    )
    assert order_resp.status_code == 200, f"Order: {order_resp.json()}"
    order_codigo = order_resp.json()["codigo"]

    # Create receivable for the order
    _create_receivable(client, headers, order_codigo, client_codigo, total)

    return order_codigo


class TestPaymentContract:
    """P1-01: Verify order_codigo comes from path, not body."""

    def test_payment_without_order_codigo_in_body(self, client, admin_token):
        """POST /finance/orders/{order_codigo}/payments accepts body WITHOUT order_codigo."""
        headers = auth_header(admin_token)
        order_codigo = _create_order(client, headers, "contract1")

        resp = client.post(
            f"/finance/orders/{order_codigo}/payments",
            json={"amount": 50.00, "method": "PIX"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert data["payment"]["order_codigo"] == order_codigo


class TestPaymentStatusSync:
    """P1-02: Verify order.payment_status syncs correctly."""

    def test_partial_payment_sets_PARTIAL(self, client, admin_token):
        """Order total=100, pay 40 → payment_status = PARTIAL."""
        headers = auth_header(admin_token)
        order_codigo = _create_order(client, headers, "partial")

        resp = client.post(
            f"/finance/orders/{order_codigo}/payments",
            json={"amount": 40.00, "method": "CASH"},
            headers=headers,
        )
        assert resp.status_code == 200

        order_resp = client.get(f"/orders/{order_codigo}", headers=headers)
        assert order_resp.status_code == 200
        assert order_resp.json()["payment_status"] == "PARTIAL"

        rec_resp = client.get(
            "/finance/receivables",
            params={"order_codigo": order_codigo},
            headers=headers,
        )
        assert rec_resp.status_code == 200
        items = rec_resp.json()["items"]
        assert len(items) == 1
        assert items[0]["status"] == "PARTIAL"
        assert float(items[0]["paid_amount"]) == 40.00
        assert float(items[0]["remaining_amount"]) == 60.00

    def test_full_payment_sets_PAID(self, client, admin_token):
        """Order total=100, pay 100 → payment_status = PAID."""
        headers = auth_header(admin_token)
        order_codigo = _create_order(client, headers, "full")

        resp = client.post(
            f"/finance/orders/{order_codigo}/payments",
            json={"amount": 100.00, "method": "PIX"},
            headers=headers,
        )
        assert resp.status_code == 200

        order_resp = client.get(f"/orders/{order_codigo}", headers=headers)
        assert order_resp.json()["payment_status"] == "PAID"

        rec_resp = client.get(
            "/finance/receivables",
            params={"order_codigo": order_codigo},
            headers=headers,
        )
        items = rec_resp.json()["items"]
        assert items[0]["status"] == "PAID"
        assert float(items[0]["remaining_amount"]) == 0.00

    def test_multiple_payments_full_coverage(self, client, admin_token):
        """Order total=100, pay 40 then 60 → PAID."""
        headers = auth_header(admin_token)
        order_codigo = _create_order(client, headers, "multi")

        resp1 = client.post(
            f"/finance/orders/{order_codigo}/payments",
            json={"amount": 40.00, "method": "CASH"},
            headers=headers,
        )
        assert resp1.status_code == 200

        resp2 = client.post(
            f"/finance/orders/{order_codigo}/payments",
            json={"amount": 60.00, "method": "PIX"},
            headers=headers,
        )
        assert resp2.status_code == 200

        order_resp = client.get(f"/orders/{order_codigo}", headers=headers)
        assert order_resp.json()["payment_status"] == "PAID"

    def test_overpayment_rejected(self, client, admin_token):
        """Order total=100, pay 80 then 30 → second rejected."""
        headers = auth_header(admin_token)
        order_codigo = _create_order(client, headers, "overpay")

        resp1 = client.post(
            f"/finance/orders/{order_codigo}/payments",
            json={"amount": 80.00, "method": "CASH"},
            headers=headers,
        )
        assert resp1.status_code == 200

        resp2 = client.post(
            f"/finance/orders/{order_codigo}/payments",
            json={"amount": 30.00, "method": "CASH"},
            headers=headers,
        )
        assert resp2.status_code == 400
        assert "exceeds" in resp2.json()["detail"].lower()


class TestIdempotency:
    """P2-02: Same key → same payment; different key → different payment."""

    def test_same_key_returns_existing(self, client, admin_token):
        """Two payments with same idempotency_key → second returns already_exists."""
        headers = auth_header(admin_token)
        order_codigo = _create_order(client, headers, "idem1")
        key = "test-idempotency-key-001"

        resp1 = client.post(
            f"/finance/orders/{order_codigo}/payments",
            json={"amount": 50.00, "method": "PIX", "idempotency_key": key},
            headers=headers,
        )
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "created"

        resp2 = client.post(
            f"/finance/orders/{order_codigo}/payments",
            json={"amount": 50.00, "method": "PIX", "idempotency_key": key},
            headers=headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "already_exists"

    def test_different_keys_create_different_payments(self, client, admin_token):
        """Two payments with different keys → both created."""
        headers = auth_header(admin_token)
        order_codigo = _create_order(client, headers, "idem2")

        resp1 = client.post(
            f"/finance/orders/{order_codigo}/payments",
            json={"amount": 50.00, "method": "CASH", "idempotency_key": "key-A"},
            headers=headers,
        )
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "created"

        resp2 = client.post(
            f"/finance/orders/{order_codigo}/payments",
            json={"amount": 50.00, "method": "PIX", "idempotency_key": "key-B"},
            headers=headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "created"

        # Verify both payments exist
        pay_resp = client.get(
            "/finance/payments",
            params={"order_codigo": order_codigo},
            headers=headers,
        )
        assert pay_resp.status_code == 200
        assert pay_resp.json()["total"] == 2
