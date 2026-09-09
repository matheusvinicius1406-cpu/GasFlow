"""
Coupon Domain + API Tests — Promoções e Cupons.

Cobre: cálculo puro (percentage/fixed/free-shipping, caps), validação
(expirado, mínimo, limite global/por cliente, restrições), CRUD, apply/remove
em pedido real e relatório de uso.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi.testclient import TestClient

from app.main import app
from app.domain.coupon.models import (
    CouponSnapshot,
    OrderContext,
    CouponValidationError,
    CouponType,
    calculate_discount,
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200
    return res.json()["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Domínio puro ─────────────────────────────────────


def _d(v):
    return Decimal(str(v)) if v is not None else None


def _coupon(**kw) -> CouponSnapshot:
    now = datetime.utcnow()
    base = dict(
        id="c1",
        code="TESTE",
        type=CouponType.PERCENTAGE,
        value=Decimal("10"),
        min_order_value=Decimal("0"),
        max_discount=None,
        applicable_products=[],
        applicable_customers=[],
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=1),
        usage_limit=0,
        usage_per_customer=1,
        usage_count=0,
    )
    for k in ("value", "min_order_value", "max_discount"):
        if k in kw:
            kw[k] = _d(kw[k])
    base.update(kw)
    return CouponSnapshot(**base)


def _ctx(subtotal="100", fee="10", products=("P1",), **kw) -> OrderContext:
    return OrderContext(
        subtotal=Decimal(subtotal),
        delivery_fee=Decimal(fee),
        product_codigos=list(products),
        client_codigo=kw.pop("client_codigo", "CL1"),
        **kw,
    )


class TestCouponCalculation:
    def test_percentage(self):
        app = calculate_discount(_coupon(value="10"), _ctx())
        assert app.discount_amount == Decimal("10.00")
        assert app.new_total == Decimal("100.00")

    def test_percentage_capped_by_max_discount(self):
        app = calculate_discount(_coupon(value="50", max_discount="30"), _ctx(subtotal="100"))
        assert app.discount_amount == Decimal("30.00")

    def test_percentage_capped_by_subtotal(self):
        app = calculate_discount(_coupon(value="150"), _ctx(subtotal="40"))
        assert app.discount_amount == Decimal("40.00")

    def test_fixed(self):
        app = calculate_discount(_coupon(type=CouponType.FIXED, value="15"), _ctx())
        assert app.discount_amount == Decimal("15.00")
        assert app.new_total == Decimal("95.00")

    def test_fixed_capped_at_total(self):
        app = calculate_discount(_coupon(type=CouponType.FIXED, value="500"), _ctx())
        assert app.discount_amount == Decimal("110.00")  # subtotal+fee

    def test_free_shipping(self):
        app = calculate_discount(_coupon(type=CouponType.FREE_SHIPPING), _ctx(fee="18.50"))
        # Frete zerado; economia vai em fee_saved (não em discount — evita 2x)
        assert app.discount_amount == Decimal("0.00")
        assert app.fee_saved == Decimal("18.50")
        assert app.new_delivery_fee == Decimal("0.00")
        assert app.new_total == Decimal("100.00")  # 100 subtotal + 0 frete


class TestCouponValidation:
    def test_expired(self):
        with pytest.raises(CouponValidationError) as e:
            calculate_discount(_coupon(end_date=datetime.utcnow() - timedelta(hours=1)), _ctx())
        assert e.value.code == "EXPIRED"

    def test_not_started(self):
        with pytest.raises(CouponValidationError) as e:
            calculate_discount(_coupon(start_date=datetime.utcnow() + timedelta(days=1)), _ctx())
        assert e.value.code == "NOT_STARTED"

    def test_inactive(self):
        with pytest.raises(CouponValidationError) as e:
            calculate_discount(_coupon(is_active=False), _ctx())
        assert e.value.code == "INACTIVE"

    def test_usage_limit(self):
        with pytest.raises(CouponValidationError) as e:
            calculate_discount(_coupon(usage_limit=10, usage_count=10), _ctx())
        assert e.value.code == "USAGE_LIMIT"

    def test_per_customer_limit(self):
        with pytest.raises(CouponValidationError) as e:
            calculate_discount(_coupon(usage_per_customer=1), _ctx(customer_usage_count=1))
        assert e.value.code == "PER_CUSTOMER_LIMIT"

    def test_product_restriction(self):
        with pytest.raises(CouponValidationError) as e:
            calculate_discount(_coupon(applicable_products=["P9"]), _ctx(products=("P1",)))
        assert e.value.code == "PRODUCT_NOT_ALLOWED"

    def test_product_restriction_ok(self):
        app = calculate_discount(_coupon(applicable_products=["P9", "P1"]), _ctx())
        assert app.discount_amount == Decimal("10.00")

    def test_customer_restriction(self):
        with pytest.raises(CouponValidationError) as e:
            calculate_discount(_coupon(applicable_customers=["CL9"]), _ctx(client_codigo="CL1"))
        assert e.value.code == "CUSTOMER_NOT_ALLOWED"

    def test_min_order_value(self):
        with pytest.raises(CouponValidationError) as e:
            calculate_discount(_coupon(min_order_value="200"), _ctx(subtotal="100"))
        assert e.value.code == "MIN_ORDER_VALUE"


# ── API ──────────────────────────────────────────────


class TestCouponAPI:
    def test_requires_auth(self, client):
        assert client.get("/coupons").status_code == 401
        assert client.post("/coupons", json={}).status_code in (401, 422)

    def test_crud_lifecycle(self, client, admin_token):
        # create
        res = client.post(
            "/coupons",
            json={
                "code": "bemvindo10",
                "name": "Bem-vindo 10%",
                "type": "PERCENTAGE",
                "value": 10,
                "min_order_value": 50,
                "end_date": (datetime.utcnow() + timedelta(days=30)).isoformat(),
                "usage_limit": 100,
                "usage_per_customer": 1,
            },
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        coupon = res.json()
        assert coupon["code"] == "BEMVINDO10"  # normalizado p/ upper
        assert coupon["is_active"] is True

        # read list + detail
        lst = client.get("/coupons", headers=_auth(admin_token)).json()["coupons"]
        assert any(c["code"] == "BEMVINDO10" for c in lst)
        one = client.get(f"/coupons/{coupon['id']}", headers=_auth(admin_token))
        assert one.status_code == 200

        # update
        upd = client.put(
            f"/coupons/{coupon['id']}",
            json={"name": "Bem-vindo 12%", "min_order_value": 30},
            headers=_auth(admin_token),
        )
        assert upd.status_code == 200
        assert upd.json()["name"] == "Bem-vindo 12%"

        # delete soft
        dele = client.delete(f"/coupons/{coupon['id']}", headers=_auth(admin_token))
        assert dele.status_code == 200
        assert dele.json()["is_active"] is False

    def test_create_validations(self, client, admin_token):
        # código duplicado (BEMVINDO10 já criado acima — inactive, mas existe)
        res = client.post(
            "/coupons",
            json={
                "code": "BEMVINDO10",
                "type": "FIXED",
                "value": 5,
                "end_date": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            },
            headers=_auth(admin_token),
        )
        assert res.status_code == 409

        # tipo inválido
        res = client.post(
            "/coupons",
            json={
                "code": "TIPOX",
                "type": "MAGIC",
                "end_date": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            },
            headers=_auth(admin_token),
        )
        assert res.status_code == 422

        # percentual > 100
        res = client.post(
            "/coupons",
            json={
                "code": "P200",
                "type": "PERCENTAGE",
                "value": 150,
                "end_date": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            },
            headers=_auth(admin_token),
        )
        assert res.status_code == 422

    def test_validate_without_order(self, client, admin_token):
        client.post(
            "/coupons",
            json={
                "code": "PREVIA",
                "type": "PERCENTAGE",
                "value": 25,
                "max_discount": 20,
                "end_date": (datetime.utcnow() + timedelta(days=7)).isoformat(),
            },
            headers=_auth(admin_token),
        )
        res = client.get(
            "/coupons/validate/PREVIA",
            params={"order_total": 100, "delivery_fee": 10},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200
        body = res.json()
        assert body["valid"] is True
        assert body["discount_amount"] == 20.0  # cap max_discount
        assert body["new_total"] == 90.0

        # inválida: abaixo do mínimo
        client.post(
            "/coupons",
            json={
                "code": "MIN50",
                "type": "FIXED",
                "value": 5,
                "min_order_value": 50,
                "end_date": (datetime.utcnow() + timedelta(days=7)).isoformat(),
            },
            headers=_auth(admin_token),
        )
        res = client.get(
            "/coupons/validate/MIN50",
            params={"order_total": 30},
            headers=_auth(admin_token),
        )
        body = res.json()
        assert body["valid"] is False
        assert body["code"] == "MIN_ORDER_VALUE"

    def test_validate_unknown_code(self, client, admin_token):
        res = client.get("/coupons/validate/NAOEXISTE", params={"order_total": 100}, headers=_auth(admin_token))
        assert res.status_code == 404

    def test_apply_and_remove_on_order(self, client, admin_token):
        # cria cliente, produto e pedido reais
        c = client.post(
            "/clients/",
            json={
                "nome": "Cliente Cupom",
                "telefone": "11999990000",
                "rua": "Rua A",
                "numero": "100",
                "bairro": "Centro",
            },
            headers=_auth(admin_token),
        )
        assert c.status_code in (200, 201), c.text
        client_codigo = c.json()["codigo"]

        p = client.post(
            "/products/",
            json={"nome": "Botijao P13 Cupom", "preco": 100.0, "tipo": "GAS"},
            headers=_auth(admin_token),
        )
        assert p.status_code in (200, 201), p.text
        product_codigo = p.json()["codigo"]

        # garante estoque (criação de pedido valida disponibilidade)
        e = client.post(
            f"/inventory/{product_codigo}/entries",
            json={"quantity": 10, "reason": "teste cupom"},
            headers=_auth(admin_token),
        )
        assert e.status_code in (200, 201), e.text

        o = client.post(
            "/orders/",
            json={
                "client_codigo": client_codigo,
                "items": [{"product_codigo": product_codigo, "quantity": 1}],
                "delivery_fee": 15.0,
                "payment_method": "PIX",
            },
            headers=_auth(admin_token),
        )
        assert o.status_code == 200, o.text
        order = o.json()
        order_codigo = order["codigo"]
        assert float(order["total"]) == 115.0

        # cupom 10% (cap 12) sobre subtotal 100 → 10 de desconto
        client.post(
            "/coupons",
            json={
                "code": "PEDIDO10",
                "type": "PERCENTAGE",
                "value": 10,
                "max_discount": 12,
                "end_date": (datetime.utcnow() + timedelta(days=7)).isoformat(),
            },
            headers=_auth(admin_token),
        )

        # aplica via rota do plano /orders/apply-coupon
        res = client.post(
            "/orders/apply-coupon",
            json={"order_codigo": order_codigo, "code": "PEDIDO10"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["discount_amount"] == 10.0
        assert body["new_total"] == 105.0

        # pedido reflete desconto
        got = client.get(f"/orders/{order_codigo}", headers=_auth(admin_token)).json()
        assert float(got["discount"]) == 10.0
        assert float(got["total"]) == 105.0

        # não acumulável: segundo cupom no mesmo pedido → 409
        client.post(
            "/coupons",
            json={
                "code": "OUTRO",
                "type": "FIXED",
                "value": 5,
                "end_date": (datetime.utcnow() + timedelta(days=7)).isoformat(),
            },
            headers=_auth(admin_token),
        )
        res = client.post(
            "/orders/apply-coupon",
            json={"order_codigo": order_codigo, "code": "OUTRO"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 409

        # relatório de uso
        rep = client.get("/coupons/reports/usage", headers=_auth(admin_token)).json()["report"]
        entry = next(r for r in rep if r["code"] == "PEDIDO10")
        assert entry["uses"] == 1
        assert entry["total_discount"] == 10.0

        # remove — restaura total
        res = client.post(f"/orders/{order_codigo}/remove-coupon", headers=_auth(admin_token))
        assert res.status_code == 200, res.text
        assert res.json()["restored_total"] == 115.0

        got = client.get(f"/orders/{order_codigo}", headers=_auth(admin_token)).json()
        assert float(got["discount"]) == 0.0
        assert float(got["total"]) == 115.0

        # resgates listados (histórico mantém o resgate removido)
        red = client.get("/coupons/reports/redemptions", headers=_auth(admin_token)).json()
        assert isinstance(red["redemptions"], list)

    def test_apply_order_not_found(self, client, admin_token):
        client.post(
            "/coupons",
            json={
                "code": "FANTASMA",
                "type": "FIXED",
                "value": 5,
                "end_date": (datetime.utcnow() + timedelta(days=7)).isoformat(),
            },
            headers=_auth(admin_token),
        )
        res = client.post(
            "/orders/apply-coupon",
            json={"order_codigo": "NAOEXISTE-999", "code": "FANTASMA"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 404
