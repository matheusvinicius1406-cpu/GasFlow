"""
OrderItem Repository Implementation — Implementação SQLAlchemy do repositório de itens de pedido.
"""

from typing import List
from sqlalchemy.orm import Session
from app.domain.order_item.entity import OrderItem
from app.domain.order_item.repository import OrderItemRepository
from app.infrastructure.repositories.order_item_model import OrderItemModel
from app.infrastructure.repositories.tenant_mixin import TenantMixin


class SQLAlchemyOrderItemRepository(TenantMixin, OrderItemRepository):
    """Implementação do repositório de itens de pedido usando SQLAlchemy."""

    def __init__(self, db: Session, tenant_id: str = "default"):
        super().__init__(db, tenant_id)

    def _to_entity(self, model: OrderItemModel) -> OrderItem:
        return OrderItem(
            id=model.id,
            order_codigo=model.order_codigo,
            product_codigo=model.product_codigo,
            product_nome=model.product_nome,
            quantity=model.quantity,
            unit_price=model.unit_price,
            subtotal=model.subtotal,
            created_at=model.created_at,
        )

    def _to_model(self, entity: OrderItem) -> OrderItemModel:
        return OrderItemModel(
            order_codigo=entity.order_codigo,
            product_codigo=entity.product_codigo,
            product_nome=entity.product_nome,
            quantity=entity.quantity,
            unit_price=entity.unit_price,
            subtotal=entity.subtotal or (entity.quantity * entity.unit_price),
        )

    def criar(self, item: OrderItem) -> OrderItem:
        model = self._to_model(item)
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def listar_por_pedido(self, order_codigo: str) -> List[OrderItem]:
        models = self._filter_by_tenant(OrderItemModel).filter(OrderItemModel.order_codigo == order_codigo).all()
        return [self._to_entity(m) for m in models]

    def deletar_por_pedido(self, order_codigo: str) -> int:
        result = self._filter_by_tenant(OrderItemModel).filter(OrderItemModel.order_codigo == order_codigo).delete()
        self.db.commit()
        return result
