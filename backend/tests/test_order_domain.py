"""
FASE 3.2 — Order Security + Financial Hardening Tests
======================================================
Tests that prove the Order domain is financially secure and immutable.
"""
import pytest


# ═══════════════════════════════════════════════════════════
# STATUS TRANSITIONS
# ═══════════════════════════════════════════════════════════

def test_order_status_transitions():
    """Full lifecycle: PENDING → CONFIRMED → PREPARING → DELIVERING → DELIVERED."""
    from app.domain.order.entity import Order, OrderStatus

    order = Order(
        codigo="000001", client_codigo="C00001",
        address_snapshot="Rua A, 123",
        subtotal=100.0, delivery_fee=10.0, discount=5.0, total=105.0,
        payment_method="PIX", payment_status="PENDING",
        source="WHATSAPP", status=OrderStatus.PENDING,
    )
    order.confirmar()
    assert order.status == OrderStatus.CONFIRMED
    order.preparar()
    assert order.status == OrderStatus.PREPARING
    order.enviar()
    assert order.status == OrderStatus.DELIVERING
    order.entregar()
    assert order.status == OrderStatus.DELIVERED


def test_order_cancelamento_from_pending():
    """Cancel from PENDING."""
    from app.domain.order.entity import Order, OrderStatus

    order = Order(
        codigo="000002", client_codigo="C00001",
        address_snapshot="Rua B",
        subtotal=50.0, delivery_fee=0.0, discount=0.0, total=50.0,
        payment_method="PIX", payment_status="PENDING",
        source="WEB", status=OrderStatus.PENDING,
    )
    order.cancelar()
    assert order.status == OrderStatus.CANCELLED


def test_order_cancelamento_from_confirmed():
    """Cancel from CONFIRMED."""
    from app.domain.order.entity import Order, OrderStatus

    order = Order(
        codigo="000006", client_codigo="C00001",
        address_snapshot="Rua C",
        subtotal=80.0, delivery_fee=5.0, discount=0.0, total=85.0,
        payment_method="PIX", payment_status="PAID",
        source="PHONE", status=OrderStatus.PENDING,
    )
    order.confirmar()
    order.cancelar()
    assert order.status == OrderStatus.CANCELLED


# ═══════════════════════════════════════════════════════════
# INVALID TRANSITIONS
# ═══════════════════════════════════════════════════════════

def test_invalid_transition_delivered_to_confirmed():
    """DELIVERED → CONFIRMED must raise."""
    from app.domain.order.entity import Order, OrderStatus

    order = Order(
        codigo="000003", client_codigo="C00001",
        address_snapshot="Rua D",
        subtotal=100.0, delivery_fee=0.0, discount=0.0, total=100.0,
        payment_method="PIX", payment_status="PAID",
        source="WEB", status=OrderStatus.DELIVERED,
    )
    with pytest.raises(ValueError, match="não pode ser alterado"):
        order.confirmar()


def test_invalid_transition_delivered_to_preparing():
    """DELIVERED → PREPARING must raise."""
    from app.domain.order.entity import Order, OrderStatus

    order = Order(
        codigo="000007", client_codigo="C00001",
        address_snapshot="Rua E",
        subtotal=100.0, delivery_fee=0.0, discount=0.0, total=100.0,
        payment_method="PIX", payment_status="PAID",
        source="WEB", status=OrderStatus.DELIVERED,
    )
    with pytest.raises(ValueError, match="não pode ser alterado"):
        order.preparar()


def test_invalid_transition_cancelled_to_delivering():
    """CANCELLED → DELIVERING must raise."""
    from app.domain.order.entity import Order, OrderStatus

    order = Order(
        codigo="000004", client_codigo="C00001",
        address_snapshot="Rua F",
        subtotal=100.0, delivery_fee=0.0, discount=0.0, total=100.0,
        payment_method="PIX", payment_status="PENDING",
        source="WEB", status=OrderStatus.CANCELLED,
    )
    with pytest.raises(ValueError, match="não pode ser alterado"):
        order.enviar()


def test_invalid_transition_cancelled_to_confirmed():
    """CANCELLED → CONFIRMED must raise."""
    from app.domain.order.entity import Order, OrderStatus

    order = Order(
        codigo="000008", client_codigo="C00001",
        address_snapshot="Rua G",
        subtotal=60.0, delivery_fee=0.0, discount=0.0, total=60.0,
        payment_method="DINHEIRO", payment_status="PENDING",
        source="BALCAO", status=OrderStatus.CANCELLED,
    )
    with pytest.raises(ValueError, match="não pode ser alterado"):
        order.confirmar()


# ═══════════════════════════════════════════════════════════
# IMMUTABILITY — Pós-DELIVERED/CANCELLED
# ═══════════════════════════════════════════════════════════

def test_immutable_after_delivered_cannot_assign_driver():
    """Cannot assign driver after DELIVERED."""
    from app.domain.order.entity import Order, OrderStatus

    order = Order(
        codigo="000020", client_codigo="C00001",
        address_snapshot="Rua H",
        subtotal=100.0, delivery_fee=0.0, discount=0.0, total=100.0,
        payment_method="PIX", payment_status="PAID",
        source="WEB", status=OrderStatus.DELIVERED,
    )
    with pytest.raises(ValueError, match="não pode ser alterado"):
        order.atribuir_entregador("D001")


def test_immutable_after_cancelled_cannot_confirm():
    """Cannot confirm after CANCELLED."""
    from app.domain.order.entity import Order, OrderStatus

    order = Order(
        codigo="000021", client_codigo="C00001",
        address_snapshot="Rua I",
        subtotal=50.0, delivery_fee=0.0, discount=0.0, total=50.0,
        payment_method="PIX", payment_status="PENDING",
        source="WEB", status=OrderStatus.CANCELLED,
    )
    with pytest.raises(ValueError, match="não pode ser alterado"):
        order.confirmar()


def test_immutable_after_delivered_cannot_cancel():
    """Cannot cancel after DELIVERED."""
    from app.domain.order.entity import Order, OrderStatus

    order = Order(
        codigo="000022", client_codigo="C00001",
        address_snapshot="Rua J",
        subtotal=100.0, delivery_fee=0.0, discount=0.0, total=100.0,
        payment_method="PIX", payment_status="PAID",
        source="WEB", status=OrderStatus.DELIVERED,
    )
    with pytest.raises(ValueError, match="não pode ser alterado"):
        order.cancelar()


# ═══════════════════════════════════════════════════════════
# FINANCIAL — Preço congelado
# ═══════════════════════════════════════════════════════════

def test_order_item_freeze_price():
    """OrderItem freezes unit_price at creation time."""
    from app.domain.order_item.entity import OrderItem

    item = OrderItem(
        order_codigo="000001",
        product_codigo="P13",
        product_nome="GLP P13",
        quantity=2,
        unit_price=100.0,
        subtotal=200.0,
    )
    assert item.unit_price == 100.0
    assert item.subtotal == 200.0


def test_order_item_calculate_subtotal():
    """OrderItem auto-calculates subtotal."""
    from app.domain.order_item.entity import OrderItem

    item = OrderItem(
        order_codigo="000001",
        product_codigo="P13",
        product_nome="GLP P13",
        quantity=3,
        unit_price=95.50,
    )
    assert item.subtotal == 286.50


# ═══════════════════════════════════════════════════════════
# FINANCIAL — Validações de domínio
# ═══════════════════════════════════════════════════════════

def test_order_entity_invalid_codigo():
    """Order code must be 6 digits."""
    from app.domain.order.entity import Order

    with pytest.raises(ValueError, match="6 dígitos"):
        Order(codigo="ABC", client_codigo="C00001", address_snapshot="Rua A")


def test_order_entity_empty_client():
    """Client code is required."""
    from app.domain.order.entity import Order

    with pytest.raises(ValueError, match="obrigatório"):
        Order(codigo="000099", client_codigo="", address_snapshot="Rua A")


def test_order_item_invalid_quantity_zero():
    """Quantity must be > 0."""
    from app.domain.order_item.entity import OrderItem

    with pytest.raises(ValueError, match="maior que 0"):
        OrderItem(
            order_codigo="000001", product_codigo="P13",
            product_nome="GLP P13", quantity=0, unit_price=100.0,
        )


def test_order_item_invalid_quantity_negative():
    """Quantity must not be negative."""
    from app.domain.order_item.entity import OrderItem

    with pytest.raises(ValueError, match="maior que 0"):
        OrderItem(
            order_codigo="000001", product_codigo="P13",
            product_nome="GLP P13", quantity=-5, unit_price=100.0,
        )


def test_order_item_invalid_negative_price():
    """Unit price must not be negative."""
    from app.domain.order_item.entity import OrderItem

    with pytest.raises(ValueError, match="negativo"):
        OrderItem(
            order_codigo="000001", product_codigo="P13",
            product_nome="GLP P13", quantity=1, unit_price=-10.0,
        )


def test_order_discount_exceeds_subtotal_raises():
    """discount > subtotal must raise ValueError in calcular_totais."""
    from app.domain.order.entity import Order, OrderStatus
    from app.domain.order_item.entity import OrderItem

    order = Order(
        codigo="000030", client_codigo="C00001",
        address_snapshot="Rua K",
        subtotal=0.0, delivery_fee=0.0, discount=60.0, total=0.0,
        payment_method="PIX", payment_status="PENDING",
        source="WEB", status=OrderStatus.PENDING,
    )
    item = OrderItem(
        order_codigo="000030", product_codigo="P13",
        product_nome="GLP P13", quantity=1, unit_price=50.0,
    )
    order.items = [item]

    with pytest.raises(ValueError, match="não pode exceder subtotal"):
        order.calcular_totais()


def test_order_discount_equals_subtotal_ok():
    """discount == subtotal is valid (total = delivery_fee)."""
    from app.domain.order.entity import Order, OrderStatus
    from app.domain.order_item.entity import OrderItem

    order = Order(
        codigo="000031", client_codigo="C00001",
        address_snapshot="Rua L",
        subtotal=0.0, delivery_fee=10.0, discount=50.0, total=0.0,
        payment_method="PIX", payment_status="PENDING",
        source="WEB", status=OrderStatus.PENDING,
    )
    item = OrderItem(
        order_codigo="000031", product_codigo="P13",
        product_nome="GLP P13", quantity=1, unit_price=50.0,
    )
    order.items = [item]
    order.calcular_totais()

    assert order.subtotal == 50.0
    assert order.discount == 50.0
    assert order.total == 10.0  # subtotal + delivery_fee - discount = 50 + 10 - 50


def test_order_calculate_totais():
    """Order recalculates totals from items correctly."""
    from app.domain.order.entity import Order, OrderStatus
    from app.domain.order_item.entity import OrderItem

    order = Order(
        codigo="000032", client_codigo="C00001",
        address_snapshot="Rua M",
        subtotal=0.0, delivery_fee=15.0, discount=5.0, total=0.0,
        payment_method="PIX", payment_status="PENDING",
        source="MANUAL", status=OrderStatus.PENDING,
    )
    item1 = OrderItem(
        order_codigo="000032", product_codigo="P13",
        product_nome="GLP P13", quantity=2, unit_price=100.0,
    )
    item2 = OrderItem(
        order_codigo="000032", product_codigo="AG20",
        product_nome="Agua 20L", quantity=1, unit_price=20.0,
    )
    order.items = [item1, item2]
    order.calcular_totais()

    assert order.subtotal == 220.0  # (2*100) + (1*20)
    assert order.total == 230.0     # 220 + 15 - 5


# ═══════════════════════════════════════════════════════════
# SCHEMA VALIDATIONS (Pydantic)
# ═══════════════════════════════════════════════════════════

def test_schema_order_item_create_rejects_unit_price():
    """OrderItemCreate should NOT have unit_price field."""
    from app.presentation.schemas.order import OrderItemCreate

    # Should accept only product_codigo + quantity
    item = OrderItemCreate(product_codigo="P13", quantity=2)
    assert item.product_codigo == "P13"
    assert item.quantity == 2
    assert not hasattr(item, 'unit_price') or 'unit_price' not in item.model_fields


def test_schema_order_item_create_invalid_quantity():
    """Schema rejects quantity <= 0."""
    from app.presentation.schemas.order import OrderItemCreate

    with pytest.raises(Exception):
        OrderItemCreate(product_codigo="P13", quantity=0)


def test_schema_order_item_create_negative_quantity():
    """Schema rejects negative quantity."""
    from app.presentation.schemas.order import OrderItemCreate

    with pytest.raises(Exception):
        OrderItemCreate(product_codigo="P13", quantity=-5)


def test_schema_order_item_create_empty_product():
    """Schema rejects empty product code."""
    from app.presentation.schemas.order import OrderItemCreate

    with pytest.raises(Exception):
        OrderItemCreate(product_codigo="", quantity=1)


def test_schema_order_create_empty_items():
    """Schema rejects empty items list."""
    from app.presentation.schemas.order import OrderCreate

    with pytest.raises(Exception):
        OrderCreate(
            client_codigo="C00001",
            address_snapshot="Rua A",
            items=[],
            payment_method="PIX",
            source="WEB",
        )


def test_schema_order_create_empty_client():
    """Schema rejects empty client code."""
    from app.presentation.schemas.order import OrderCreate

    with pytest.raises(Exception):
        OrderCreate(
            client_codigo="",
            items=[{"product_codigo": "P13", "quantity": 1}],
            source="WEB",
        )


def test_schema_order_create_negative_delivery_fee():
    """Schema rejects negative delivery fee."""
    from app.presentation.schemas.order import OrderCreate

    with pytest.raises(Exception):
        OrderCreate(
            client_codigo="C00001",
            items=[{"product_codigo": "P13", "quantity": 1}],
            delivery_fee=-5.0,
            source="WEB",
        )


def test_schema_order_create_negative_discount():
    """Schema rejects negative discount."""
    from app.presentation.schemas.order import OrderCreate

    with pytest.raises(Exception):
        OrderCreate(
            client_codigo="C00001",
            items=[{"product_codigo": "P13", "quantity": 1}],
            discount=-10.0,
            source="WEB",
        )


# ═══════════════════════════════════════════════════════════
# API CONTRACT
# ═══════════════════════════════════════════════════════════

def test_api_contract_order_response_fields():
    """Verify OrderResponse has all required fields."""
    from app.presentation.schemas.order import OrderResponse

    fields = OrderResponse.model_fields.keys()
    required = [
        "codigo", "client_codigo", "status", "subtotal",
        "total", "payment_status", "source", "address_snapshot",
        "delivery_fee", "discount",
    ]
    for field in required:
        assert field in fields, f"Missing field: {field}"


def test_api_contract_order_list_response():
    """Verify OrderListResponse wraps items correctly."""
    from app.presentation.schemas.order import OrderListResponse

    response = OrderListResponse(items=[], total=0, page=1, page_size=10)
    assert response.items == []
    assert response.total == 0


def test_api_contract_order_detail_response():
    """Verify OrderDetailResponse includes items."""
    from app.presentation.schemas.order import OrderDetailResponse

    fields = OrderDetailResponse.model_fields.keys()
    assert "items" in fields


def test_api_contract_order_item_no_price_in_create():
    """OrderItemCreate should NOT contain unit_price."""
    from app.presentation.schemas.order import OrderItemCreate

    fields = OrderItemCreate.model_fields.keys()
    assert "unit_price" not in fields, "unit_price should be removed from OrderItemCreate"


# ═══════════════════════════════════════════════════════════
# ADDRESS SNAPSHOT
# ═══════════════════════════════════════════════════════════

def test_order_address_snapshot_preserved():
    """Address snapshot is independent of customer current address."""
    from app.domain.order.entity import Order, OrderStatus

    order = Order(
        codigo="000005", client_codigo="C00001",
        address_snapshot="Rua Antiga, 123 - Centro",
        subtotal=80.0, delivery_fee=5.0, discount=0.0, total=85.0,
        payment_method="DINHEIRO", payment_status="PAID",
        source="BALCAO", status=OrderStatus.PENDING,
    )
    assert "Rua Antiga" in order.address_snapshot
    assert "123" in order.address_snapshot


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
