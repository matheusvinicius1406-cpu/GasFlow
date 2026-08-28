"""
Order Repository Implementation — Implementação SQLAlchemy do repositório de pedidos.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from app.domain.order.entity import Order, OrderStatus, PaymentStatus, OrderSource
from app.domain.order.repository import OrderRepository
from app.infrastructure.repositories.order_model import OrderModel
from app.infrastructure.repositories.tenant_mixin import TenantMixin


class SQLAlchemyOrderRepository(TenantMixin, OrderRepository):
    """Implementação do repositório de pedidos usando SQLAlchemy."""

    def __init__(self, db: Session, tenant_id: str = "default"):
        super().__init__(db, tenant_id)

    def _to_entity(self, model: OrderModel) -> Order:
        return Order(
            id=model.id,
            codigo=model.codigo,
            client_codigo=model.client_codigo,
            address_snapshot=model.address_snapshot or "",
            status=OrderStatus(model.status),
            subtotal=model.subtotal or 0.0,
            delivery_fee=model.delivery_fee or 0.0,
            discount=model.discount or 0.0,
            total=model.total or 0.0,
            payment_method=model.payment_method,
            payment_status=PaymentStatus(model.payment_status or "PENDING"),
            delivery_driver_codigo=model.delivery_driver_codigo,
            source=OrderSource(model.source or "MANUAL"),
            notes=model.notes,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: Order) -> OrderModel:
        if entity.id:
            model = self._filter_by_tenant(OrderModel).filter(OrderModel.id == entity.id).first()
            if model:
                model.codigo = entity.codigo
                model.client_codigo = entity.client_codigo
                model.address_snapshot = entity.address_snapshot
                model.status = entity.status.value
                model.subtotal = entity.subtotal
                model.delivery_fee = entity.delivery_fee
                model.discount = entity.discount
                model.total = entity.total
                model.payment_method = entity.payment_method
                model.payment_status = entity.payment_status.value
                model.delivery_driver_codigo = entity.delivery_driver_codigo
                model.source = entity.source.value
                model.notes = entity.notes
                return model

        return OrderModel(
            tenant_id=self.tenant_id,
            codigo=entity.codigo,
            client_codigo=entity.client_codigo,
            address_snapshot=entity.address_snapshot,
            status=entity.status.value,
            subtotal=entity.subtotal,
            delivery_fee=entity.delivery_fee,
            discount=entity.discount,
            total=entity.total,
            payment_method=entity.payment_method,
            payment_status=entity.payment_status.value,
            delivery_driver_codigo=entity.delivery_driver_codigo,
            source=entity.source.value,
            notes=entity.notes,
        )

    def criar(self, order: Order) -> Order:
        model = self._to_model(order)
        model.tenant_id = self.tenant_id
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def buscar_por_codigo(self, codigo: str) -> Optional[Order]:
        model = self._filter_by_tenant(OrderModel).filter(OrderModel.codigo == codigo).first()
        return self._to_entity(model) if model else None

    def listar_todos(self, status: Optional[OrderStatus] = None) -> List[Order]:
        query = self._filter_by_tenant(OrderModel)
        if status:
            query = query.filter(OrderModel.status == status.value)
        models = query.order_by(OrderModel.id.desc()).all()
        return [self._to_entity(m) for m in models]

    def atualizar_status(self, codigo: str, status: OrderStatus) -> Optional[Order]:
        model = self._filter_by_tenant(OrderModel).filter(OrderModel.codigo == codigo).first()
        if not model:
            return None
        model.status = status.value
        model.updated_at = __import__("datetime").datetime.utcnow()
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def atribuir_entregador(self, codigo: str, driver_codigo: str) -> Optional[Order]:
        model = self._filter_by_tenant(OrderModel).filter(OrderModel.codigo == codigo).first()
        if not model:
            return None
        model.delivery_driver_codigo = driver_codigo
        model.updated_at = __import__("datetime").datetime.utcnow()
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def proximo_codigo(self) -> str:
        last = self._filter_by_tenant(OrderModel).order_by(OrderModel.id.desc()).first()
        if not last:
            return "000001"
        return f"{int(last.codigo) + 1:06d}"

    def get_customer_metrics(self, client_codigo: str) -> dict:
        """Retorna métricas CRM derivadas dos pedidos do cliente.

        FASE 6 FIX: favorite_product now calculated from order items.
        """
        from sqlalchemy import func
        from app.infrastructure.repositories.order_item_model import OrderItemModel

        models = (
            self._filter_by_tenant(OrderModel)
            .filter(OrderModel.client_codigo == client_codigo)
            .order_by(OrderModel.created_at.asc())
            .all()
        )

        if not models:
            return {
                "total_orders": 0,
                "total_spent": 0.0,
                "average_ticket": 0.0,
                "first_order_at": None,
                "last_order_at": None,
                "days_since_last_order": None,
                "favorite_product": None,
            }

        total_orders = len(models)
        total_spent = sum(float(m.total or 0) for m in models)
        average_ticket = total_spent / total_orders if total_orders > 0 else 0.0
        first_order_at = models[0].created_at
        last_order_at = models[-1].created_at

        days_since_last_order = None
        if last_order_at:
            from datetime import datetime
            delta = datetime.utcnow() - last_order_at
            days_since_last_order = delta.days

        # FASE 6: Calculate favorite_product from order items
        favorite_product = None
        order_codes = [m.codigo for m in models]
        if order_codes:
            top_product = (
                self.db.query(
                    OrderItemModel.product_nome,
                    func.sum(OrderItemModel.quantity).label("total_qty")
                )
                .filter(OrderItemModel.tenant_id == self.tenant_id)
                .filter(OrderItemModel.order_codigo.in_(order_codes))
                .group_by(OrderItemModel.product_nome)
                .order_by(func.sum(OrderItemModel.quantity).desc())
                .first()
            )
            if top_product:
                favorite_product = top_product[0]

        return {
            "total_orders": total_orders,
            "total_spent": round(total_spent, 2),
            "average_ticket": round(average_ticket, 2),
            "first_order_at": first_order_at,
            "last_order_at": last_order_at,
            "days_since_last_order": days_since_last_order,
            "favorite_product": favorite_product,
        }

    def get_customer_orders(self, client_codigo: str) -> list:
        """Retorna pedidos do cliente para Customer 360."""
        models = (
            self._filter_by_tenant(OrderModel)
            .filter(OrderModel.client_codigo == client_codigo)
            .order_by(OrderModel.created_at.desc())
            .limit(50)
            .all()
        )
        return [self._to_entity(m) for m in models]
