"""
Receipt data — F10.7 (impressão com o pedido de verdade)

O cupom ESC/POS é montado a partir do PEDIDO REAL: itens, quantidades, preços
congelados, subtotal/entrega/desconto/total, forma de pagamento, observações,
endereço do snapshot e motorista.

Antes disto o `POST /printer/print` e o auto-print enviavam placeholders
(`client_name="Cliente"`, `client_address="Endereco"`, `items=[]`,
`total=0`): a impressão "funcionava" gerando um cupom inútil — ou seja, nada
chegava à impressora E o que chegasse estaria errado.
"""

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session as DBSession

from app.infrastructure.repositories.order_item_model import OrderItemModel
from app.infrastructure.repositories.order_model import OrderModel


class OrderNotFoundError(Exception):
    """Pedido inexistente para o tenant — não há cupom a imprimir."""


def build_receipt_data(db: DBSession, tenant_id: str, order_codigo: str) -> Dict[str, Any]:
    """Payload completo do cupom para `ReceiptFormatter.format_order`.

    Levanta `OrderNotFoundError` quando o pedido não existe (melhor falhar
    alto do que imprimir um cupom vazio).
    """
    order = db.query(OrderModel).filter(OrderModel.codigo == order_codigo, OrderModel.tenant_id == tenant_id).first()
    if order is None:
        raise OrderNotFoundError(order_codigo)

    items = (
        db.query(OrderItemModel)
        .filter(OrderItemModel.order_codigo == order_codigo, OrderItemModel.tenant_id == tenant_id)
        .order_by(OrderItemModel.id)
        .all()
    )

    return {
        "codigo": str(order.codigo),
        "client_codigo": str(order.client_codigo or ""),
        "client_name": _client_name(db, tenant_id, str(order.client_codigo or "")) or "Cliente",
        "client_address": order.address_snapshot or "",
        "items": [
            {
                "product_codigo": item.product_codigo,
                "product_nome": item.product_nome,
                "quantity": int(item.quantity or 0),
                "unit_price": _f(item.unit_price),
                "subtotal": _f(item.subtotal),
            }
            for item in items
        ],
        "subtotal": _f(order.subtotal),
        "delivery_fee": _f(order.delivery_fee),
        "discount": _f(order.discount),
        "total": _f(order.total),
        "payment_method": str(order.payment_method or ""),
        "payment_status": str(order.payment_status or ""),
        "notes": str(order.notes or ""),
        "driver_name": _driver_name(db, tenant_id, str(order.delivery_driver_codigo or "")),
        "created_at": order.created_at.isoformat() if order.created_at else "",
    }


def _f(value: Any) -> float:
    """Numeric/Decimal do banco → float (o formatador trabalha em float)."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _client_name(db: DBSession, tenant_id: str, codigo: Optional[str]) -> str:
    if not codigo:
        return ""
    try:
        from app.infrastructure.repositories.client_repository import (
            SQLAlchemyClientRepository,
        )

        client = SQLAlchemyClientRepository(db, tenant_id).buscar_por_codigo(codigo)
        return (getattr(client, "nome", "") or "").strip()
    except Exception:
        # Nome é enfeite do cupom — nunca impedir a impressão do pedido.
        return ""


def _driver_name(db: DBSession, tenant_id: str, codigo: Optional[str]) -> str:
    if not codigo:
        return ""
    try:
        from app.infrastructure.repositories.delivery_model import DeliveryDriverModel

        driver = (
            db.query(DeliveryDriverModel)
            .filter(
                DeliveryDriverModel.codigo == codigo,
                DeliveryDriverModel.tenant_id == tenant_id,
            )
            .first()
        )
        return (getattr(driver, "nome", "") or "").strip() if driver else ""
    except Exception:
        return ""
