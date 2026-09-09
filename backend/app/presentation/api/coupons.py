"""
Coupons API — Módulo de Promoções e Cupons.

Endpoints:
    GET    /coupons                       — listar (coupon.read)
    GET    /coupons/{coupon_id}           — detalhe (coupon.read)
    POST   /coupons                       — criar (coupon.write)
    PUT    /coupons/{coupon_id}           — editar (coupon.write)
    DELETE /coupons/{coupon_id}           — excluir soft (coupon.write)
    GET    /coupons/validate/{code}       — validar p/ contexto de pedido (auth)
    GET    /coupons/reports/usage         — relatório de uso (coupon.read)
    GET    /coupons/reports/redemptions   — resgates recentes (coupon.read)
    POST   /coupons/apply                 — aplicar a pedido (order.create)
    POST   /coupons/remove                — remover de pedido (order.update)

Rotas sem prefixo: /orders/apply-coupon e /orders/{codigo}/remove-coupon
também expostas aqui (mesma implementação) para compatibilidade com o plano.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional

from app.infrastructure.database.dependencies import get_db
from sqlalchemy.orm import Session

from app.application.coupon.coupon_service import CouponService, CouponServiceError
from app.domain.coupon.models import CouponValidationError
from app.infrastructure.repositories.order_model import OrderModel
from app.presentation.dependencies import (
    get_tenant_context,
    require_permission,
)
from app.domain.security.models import TenantContext

# Sem prefixo no router: os paths abaixo são absolutos dentro do app.
router = APIRouter(tags=["Coupons"])


def _svc(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context)) -> CouponService:
    return CouponService(db, ctx.tenant_id)


def _coupon_dict(c) -> dict:
    return {
        "id": c.id,
        "code": c.code,
        "name": c.name,
        "description": c.description,
        "type": c.type,
        "value": float(c.value) if c.value is not None else None,
        "min_order_value": float(c.min_order_value or 0),
        "max_discount": float(c.max_discount) if c.max_discount is not None else None,
        "applicable_products": list(c.applicable_products or []),
        "applicable_customers": list(c.applicable_customers or []),
        "start_date": c.start_date.isoformat() if c.start_date else None,
        "end_date": c.end_date.isoformat() if c.end_date else None,
        "usage_limit": c.usage_limit,
        "usage_per_customer": c.usage_per_customer,
        "usage_count": c.usage_count,
        "is_active": c.is_active,
        "created_by": c.created_by,
    }


# ── Schemas ──────────────────────────────────────────


class CouponCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    name: Optional[str] = None
    description: Optional[str] = None
    type: str
    value: Optional[float] = None
    min_order_value: float = 0
    max_discount: Optional[float] = None
    applicable_products: List[str] = Field(default_factory=list)
    applicable_customers: List[str] = Field(default_factory=list)
    start_date: Optional[str] = None
    end_date: str
    usage_limit: int = 0
    usage_per_customer: int = 1
    is_active: bool = True


class CouponUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    min_order_value: Optional[float] = None
    max_discount: Optional[float] = None
    applicable_products: Optional[List[str]] = None
    applicable_customers: Optional[List[str]] = None
    end_date: Optional[str] = None
    usage_limit: Optional[int] = None
    usage_per_customer: Optional[int] = None
    is_active: Optional[bool] = None


class ApplyCoupon(BaseModel):
    order_codigo: str
    code: str


class RemoveCoupon(BaseModel):
    order_codigo: str


# ── Rotas de cupom ───────────────────────────────────


@router.get("/coupons")
def list_coupons(
    active_only: bool = Query(default=False),
    svc: CouponService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("coupon.read")),
):
    coupons = svc.list_coupons(include_inactive=not active_only)
    return {"coupons": [_coupon_dict(c) for c in coupons]}


@router.get("/coupons/reports/usage")
def usage_report(
    svc: CouponService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("coupon.read")),
):
    return {"report": svc.usage_report()}


@router.get("/coupons/reports/redemptions")
def redemptions(
    coupon_id: Optional[str] = Query(default=None),
    limit: int = Query(default=200, le=500),
    svc: CouponService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("coupon.read")),
):
    return {"redemptions": svc.list_redemptions(coupon_id, limit)}


@router.get("/coupons/validate/{code}")
def validate_coupon(
    code: str,
    order_codigo: Optional[str] = Query(default=None),
    order_total: Optional[float] = Query(default=None),
    delivery_fee: float = Query(default=0),
    client_codigo: Optional[str] = Query(default=None),
    products: Optional[str] = Query(default=None, description="csv de product_codigo"),
    svc: CouponService = Depends(_svc),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Validação leve (pré-checkout).

    - Com order_codigo: valida contra o pedido real.
    - Sem: valida contra order_total/produtos informados (prévia).
    """
    coupon = svc.get_by_code(code)
    if not coupon:
        raise HTTPException(status_code=404, detail=f"Cupom '{code}' não encontrado.")

    if order_codigo:
        order = (
            svc.db.query(OrderModel)
            .filter(OrderModel.codigo == order_codigo, OrderModel.tenant_id == ctx.tenant_id)
            .first()
        )
        if not order:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        try:
            app_result = svc.validate_for_order(order, coupon)
        except CouponValidationError as e:
            return {"valid": False, "code": e.code, "message": e.message}
        return {
            "valid": True,
            "coupon": _coupon_dict(coupon),
            "discount_amount": float(app_result.discount_amount),
            "new_total": float(app_result.new_total),
        }

    # Prévia sem pedido: usa domínio puro.
    from decimal import Decimal
    from app.domain.coupon.models import (
        CouponSnapshot,
        OrderContext,
        calculate_discount,
    )

    snapshot = CouponSnapshot.from_model(coupon)
    product_list = [p.strip() for p in (products or "").split(",") if p.strip()]
    ctxo = OrderContext(
        subtotal=Decimal(str(order_total or 0)),
        delivery_fee=Decimal(str(delivery_fee or 0)),
        product_codigos=product_list,
        client_codigo=client_codigo,
        customer_usage_count=svc.customer_usage(coupon.id, client_codigo),
    )
    try:
        app_result = calculate_discount(snapshot, ctxo)
    except CouponValidationError as e:
        return {"valid": False, "code": e.code, "message": e.message}
    return {
        "valid": True,
        "coupon": _coupon_dict(coupon),
        "discount_amount": float(app_result.discount_amount),
        "new_total": float(app_result.new_total),
    }


@router.post("/coupons")
def create_coupon(
    body: CouponCreate,
    svc: CouponService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("coupon.write")),
):
    try:
        coupon = svc.create_coupon(body.model_dump(), created_by=ctx.user_id)
    except CouponServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return _coupon_dict(coupon)


@router.get("/coupons/{coupon_id}")
def get_coupon(
    coupon_id: str,
    svc: CouponService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("coupon.read")),
):
    coupon = svc.get_coupon(coupon_id)
    if not coupon:
        raise HTTPException(status_code=404, detail="Cupom não encontrado.")
    return _coupon_dict(coupon)


@router.put("/coupons/{coupon_id}")
def update_coupon(
    coupon_id: str,
    body: CouponUpdate,
    svc: CouponService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("coupon.write")),
):
    try:
        coupon = svc.update_coupon(coupon_id, body.model_dump(exclude_none=True))
    except CouponServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return _coupon_dict(coupon)


@router.delete("/coupons/{coupon_id}")
def delete_coupon(
    coupon_id: str,
    svc: CouponService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("coupon.write")),
):
    try:
        coupon = svc.deactivate(coupon_id)
    except CouponServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return _coupon_dict(coupon)


# ── Aplicação em pedidos ─────────────────────────────


@router.post("/coupons/apply")
def apply_coupon(
    body: ApplyCoupon,
    svc: CouponService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("order.create")),
):
    try:
        result = svc.apply_to_order(body.order_codigo, body.code, actor_id=ctx.user_id)
    except CouponServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {
        "order_codigo": result["order"].codigo,
        "code": result["coupon"].code,
        "discount_amount": float(result["discount_amount"]),
        "new_total": float(result["new_total"]),
        "delivery_fee": float(result["order"].delivery_fee or 0),
    }


@router.post("/coupons/remove")
def remove_coupon(
    body: RemoveCoupon,
    svc: CouponService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("order.update")),
):
    try:
        result = svc.remove_from_order(body.order_codigo)
    except CouponServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {
        "order_codigo": result["order"].codigo,
        "restored_total": float(result["restored_total"]),
    }


# ── Compatibilidade com o plano: rotas sob /orders ────


@router.post("/orders/apply-coupon")
def apply_coupon_orders_path(
    body: ApplyCoupon,
    svc: CouponService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("order.create")),
):
    return apply_coupon(body, svc, ctx)


@router.post("/orders/{order_codigo}/remove-coupon")
def remove_coupon_orders_path(
    order_codigo: str,
    svc: CouponService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("order.update")),
):
    return remove_coupon(RemoveCoupon(order_codigo=order_codigo), svc, ctx)
