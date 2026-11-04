"""Regressão: item de pedido precisa nascer no tenant do repositório.

Histórico do defeito (03/11/2026, Home Server): `_to_model` não passava
`tenant_id`, então a coluna caía no default ``"default"``. Como toda leitura
é filtrada por tenant, o item ficava invisível no tenant real; e porque o
código do pedido reinicia a cada tenant (000001, 000002...), itens de tenants
distintos passavam a colidir no mesmo bucket ``default``.

Este teste trava o contrato no ponto exato da falha, sem precisar de banco.
"""

from app.domain.order_item.entity import OrderItem
from app.infrastructure.repositories.order_item_repository import (
    SQLAlchemyOrderItemRepository,
)


def _item() -> OrderItem:
    return OrderItem(
        order_codigo="000001",
        product_codigo="000005",
        product_nome="Gás P13",
        quantity=2,
        unit_price=120.0,
    )


def test_to_model_grava_tenant_do_repositorio():
    repo = SQLAlchemyOrderItemRepository(db=None, tenant_id="loja_a")

    model = repo._to_model(_item())

    assert model.tenant_id == "loja_a"


def test_to_model_preserva_campos_do_item():
    repo = SQLAlchemyOrderItemRepository(db=None, tenant_id="loja_a")

    model = repo._to_model(_item())

    assert model.order_codigo == "000001"
    assert model.product_codigo == "000005"
    assert model.quantity == 2
    assert float(model.subtotal) == 240.0
