"""
Coupon Service — CRUD e aplicação de cupons em pedidos.

Camada de aplicação: orquestra repositórios (SQLAlchemy) e o domínio puro
(app.domain.coupon.models) que faz validação/cálculo.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session as DBSession

from app.domain.coupon.models import (
    CouponApplication,
    CouponSnapshot,
    CouponType,
    OrderContext,
    calculate_discount,
)
from app.infrastructure.repositories.coupon_model import CouponModel, CouponRedemptionModel
from app.infrastructure.repositories.order_model import OrderModel
from app.infrastructure.repositories.order_item_model import OrderItemModel


class CouponServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _to_d(value) -> Decimal:
    return Decimal(str(value or 0))


class CouponService:
    def __init__(self, db: DBSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    # ── Queries ──────────────────────────────────────────

    def list_coupons(self, include_inactive: bool = True) -> List[CouponModel]:
        q = self.db.query(CouponModel).filter(CouponModel.tenant_id == self.tenant_id)
        if not include_inactive:
            q = q.filter(CouponModel.is_active.is_(True))
        return q.order_by(CouponModel.created_at.desc()).all()

    def get_coupon(self, coupon_id: str) -> Optional[CouponModel]:
        return (
            self.db.query(CouponModel)
            .filter(CouponModel.id == coupon_id, CouponModel.tenant_id == self.tenant_id)
            .first()
        )

    def get_by_code(self, code: str) -> Optional[CouponModel]:
        return (
            self.db.query(CouponModel)
            .filter(CouponModel.code == code.strip().upper(), CouponModel.tenant_id == self.tenant_id)
            .first()
        )

    def customer_usage(self, coupon_id: str, client_codigo: Optional[str]) -> int:
        """Resgates anteriores deste cliente neste cupom."""
        if not client_codigo:
            return 0
        return (
            self.db.query(CouponRedemptionModel)
            .filter(
                CouponRedemptionModel.coupon_id == coupon_id,
                CouponRedemptionModel.client_codigo == client_codigo,
                CouponRedemptionModel.tenant_id == self.tenant_id,
            )
            .count()
        )

    _customer_usage = customer_usage  # alias interno

    # ── CRUD ─────────────────────────────────────────────

    def create_coupon(self, data: dict, created_by: str = "") -> CouponModel:
        code = (data.get("code") or "").strip().upper()
        if not code:
            raise CouponServiceError("CODE_REQUIRED", "Código do cupom é obrigatório.")
        if self.get_by_code(code):
            raise CouponServiceError("DUPLICATE_CODE", f"Cupom '{code}' já existe.", 409)

        ctype = data.get("type")
        if ctype not in CouponType.ALL:
            raise CouponServiceError("INVALID_TYPE", f"Tipo deve ser um de: {', '.join(CouponType.ALL)}.")
        value = data.get("value")
        if ctype in (CouponType.PERCENTAGE, CouponType.FIXED):
            if value is None or _to_d(value) <= 0:
                raise CouponServiceError("VALUE_REQUIRED", "Valor do cupom é obrigatório.")
        if ctype == CouponType.PERCENTAGE and _to_d(value) > 100:
            raise CouponServiceError("INVALID_PERCENTAGE", "Percentual não pode exceder 100.")

        start = data.get("start_date") or datetime.utcnow()
        end = data.get("end_date")
        if not end:
            raise CouponServiceError("END_DATE_REQUIRED", "Validade final é obrigatória.")
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.fromisoformat(end)
        if end <= start:
            raise CouponServiceError("INVALID_PERIOD", "end_date deve ser posterior a start_date.")

        coupon = CouponModel(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            code=code,
            name=data.get("name"),
            description=data.get("description"),
            type=ctype,
            value=_to_d(value) if value is not None else None,
            min_order_value=_to_d(data.get("min_order_value", 0)),
            max_discount=_to_d(data["max_discount"]) if data.get("max_discount") is not None else None,
            applicable_products=list(data.get("applicable_products") or []),
            applicable_customers=list(data.get("applicable_customers") or []),
            start_date=start,
            end_date=end,
            usage_limit=int(data.get("usage_limit") or 0),
            usage_per_customer=int(data.get("usage_per_customer") or 1),
            usage_count=0,
            is_active=bool(data.get("is_active", True)),
            created_by=created_by,
        )
        self.db.add(coupon)
        self.db.commit()
        self.db.refresh(coupon)
        return coupon

    def update_coupon(self, coupon_id: str, data: dict) -> CouponModel:
        coupon = self.get_coupon(coupon_id)
        if not coupon:
            raise CouponServiceError("NOT_FOUND", "Cupom não encontrado.", 404)

        editable = {
            "name",
            "description",
            "min_order_value",
            "max_discount",
            "applicable_products",
            "applicable_customers",
            "usage_limit",
            "usage_per_customer",
            "is_active",
        }
        for field in editable:
            if field in data and data[field] is not None:
                v = data[field]
                if field in ("min_order_value", "max_discount") and v is not None:
                    v = _to_d(v)
                setattr(coupon, field, v)

        if "end_date" in data and data["end_date"]:
            end = data["end_date"]
            if isinstance(end, str):
                end = datetime.fromisoformat(end)
            if end <= coupon.start_date:
                raise CouponServiceError("INVALID_PERIOD", "end_date deve ser posterior a start_date.")
            coupon.end_date = end

        self.db.commit()
        self.db.refresh(coupon)
        return coupon

    def deactivate(self, coupon_id: str) -> CouponModel:
        """Exclusão soft: is_active=False."""
        coupon = self.get_coupon(coupon_id)
        if not coupon:
            raise CouponServiceError("NOT_FOUND", "Cupom não encontrado.", 404)
        coupon.is_active = False
        self.db.commit()
        self.db.refresh(coupon)
        return coupon

    # ── Validação / aplicação ────────────────────────────

    def _order_context(self, order: OrderModel, coupon: CouponModel) -> OrderContext:
        items = (
            self.db.query(OrderItemModel)
            .filter(
                OrderItemModel.order_codigo == order.codigo,
                OrderItemModel.tenant_id == self.tenant_id,
            )
            .all()
        )
        return OrderContext(
            subtotal=_to_d(order.subtotal),
            delivery_fee=_to_d(order.delivery_fee),
            product_codigos=[i.product_codigo for i in items],
            client_codigo=order.client_codigo,
            customer_usage_count=self._customer_usage(coupon.id, order.client_codigo),
        )

    def validate_for_order(self, order: OrderModel, coupon: CouponModel) -> CouponApplication:
        """Valida e retorna a aplicação sem persistir nada."""
        snapshot = CouponSnapshot.from_model(coupon)
        ctx = self._order_context(order, coupon)
        return calculate_discount(snapshot, ctx)

    def apply_to_order(self, order_codigo: str, code: str, actor_id: str = "") -> dict:
        """Aplica o cupom ao pedido: recalcula totals, registra resgate.

        Um cupom por pedido (constraint unique em coupon_redemptions).
        """
        order = (
            self.db.query(OrderModel)
            .filter(OrderModel.codigo == order_codigo, OrderModel.tenant_id == self.tenant_id)
            .first()
        )
        if not order:
            raise CouponServiceError("ORDER_NOT_FOUND", "Pedido não encontrado.", 404)

        existing = (
            self.db.query(CouponRedemptionModel)
            .filter(
                CouponRedemptionModel.order_codigo == order_codigo,
                CouponRedemptionModel.tenant_id == self.tenant_id,
            )
            .first()
        )
        if existing:
            raise CouponServiceError("ALREADY_APPLIED", "Pedido já possui cupom aplicado (não acumulável).", 409)

        coupon = self.get_by_code(code)
        if not coupon:
            raise CouponServiceError("NOT_FOUND", f"Cupom '{code}' não encontrado.", 404)

        app_result = self.validate_for_order(order, coupon)

        delivery_fee_before = _to_d(order.delivery_fee)
        order.discount = _to_d(order.discount) + app_result.discount_amount
        order.delivery_fee = app_result.new_delivery_fee
        order.total = app_result.new_total

        redemption = CouponRedemptionModel(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            coupon_id=coupon.id,
            order_codigo=order.codigo,
            client_codigo=order.client_codigo,
            discount_amount=app_result.discount_amount,
            fee_saved=app_result.fee_saved,
            delivery_fee_before=delivery_fee_before,
        )
        coupon.usage_count = (coupon.usage_count or 0) + 1
        self.db.add(redemption)
        self.db.commit()
        self.db.refresh(order)
        return {
            "order": order,
            "coupon": coupon,
            "discount_amount": app_result.discount_amount,
            "new_total": app_result.new_total,
        }

    def remove_from_order(self, order_codigo: str) -> dict:
        """Remove o cupom do pedido e restaura os valores originais."""
        order = (
            self.db.query(OrderModel)
            .filter(OrderModel.codigo == order_codigo, OrderModel.tenant_id == self.tenant_id)
            .first()
        )
        if not order:
            raise CouponServiceError("ORDER_NOT_FOUND", "Pedido não encontrado.", 404)

        redemption = (
            self.db.query(CouponRedemptionModel)
            .filter(
                CouponRedemptionModel.order_codigo == order_codigo,
                CouponRedemptionModel.tenant_id == self.tenant_id,
            )
            .first()
        )
        if not redemption:
            raise CouponServiceError("NO_COUPON", "Pedido não possui cupom aplicado.", 404)

        coupon = self.db.query(CouponModel).filter(CouponModel.id == redemption.coupon_id).first()
        if coupon:
            coupon.usage_count = max(0, (coupon.usage_count or 0) - 1)

        order.discount = _to_d(order.discount) - _to_d(redemption.discount_amount)
        order.delivery_fee = _to_d(redemption.delivery_fee_before)
        order.total = _to_d(order.subtotal) + _to_d(order.delivery_fee) - _to_d(order.discount)

        self.db.delete(redemption)
        self.db.commit()
        self.db.refresh(order)
        return {"order": order, "restored_total": _to_d(order.total)}

    def usage_report(self) -> List[dict]:
        """Relatório de uso: agregado por cupom (descontos + fretes pagos pelo cupom)."""
        redemptions = (
            self.db.query(CouponRedemptionModel).filter(CouponRedemptionModel.tenant_id == self.tenant_id).all()
        )
        by_coupon: dict = {}
        for r in redemptions:
            agg = by_coupon.setdefault(
                r.coupon_id, {"coupon_id": r.coupon_id, "uses": 0, "total_discount": Decimal("0.00")}
            )
            agg["uses"] += 1
            agg["total_discount"] += _to_d(r.discount_amount) + _to_d(getattr(r, "fee_saved", 0))

        result = []
        for agg in by_coupon.values():
            coupon = self.db.query(CouponModel).filter(CouponModel.id == agg["coupon_id"]).first()
            result.append(
                {
                    "coupon_id": agg["coupon_id"],
                    "code": coupon.code if coupon else "?",
                    "name": coupon.name if coupon else None,
                    "type": coupon.type if coupon else None,
                    "uses": agg["uses"],
                    "total_discount": float(agg["total_discount"]),
                }
            )
        result.sort(key=lambda x: -x["uses"])
        return result

    def list_redemptions(self, coupon_id: Optional[str] = None, limit: int = 200) -> List[dict]:
        q = self.db.query(CouponRedemptionModel).filter(CouponRedemptionModel.tenant_id == self.tenant_id)
        if coupon_id:
            q = q.filter(CouponRedemptionModel.coupon_id == coupon_id)
        rows = q.order_by(CouponRedemptionModel.created_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "coupon_id": r.coupon_id,
                "order_codigo": r.order_codigo,
                "client_codigo": r.client_codigo,
                "discount_amount": float(_to_d(r.discount_amount)),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
