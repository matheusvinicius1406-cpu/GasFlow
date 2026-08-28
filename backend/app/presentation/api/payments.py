"""
Payments API — GasFlow

Endpoints for payment methods, PIX configuration, and payment lifecycle.

Endpoints:
    GET    /payments/methods — List payment methods
    POST   /payments/methods — Create payment method
    PATCH  /payments/methods/{id} — Update payment method
    DELETE /payments/methods/{id} — Delete payment method
    PATCH  /payments/methods/{id}/toggle — Enable/disable method

    GET    /payments/pix — Get PIX configuration
    POST   /payments/pix — Create PIX configuration
    PATCH  /payments/pix/{id} — Update PIX configuration
    DELETE /payments/pix/{id} — Delete PIX configuration

    GET    /payments — List payments
    POST   /payments — Create payment
    GET    /payments/{id} — Get payment detail
    POST   /payments/{id}/confirm — Confirm payment
    POST   /payments/{id}/cancel — Cancel payment
    POST   /payments/{id}/refund — Refund payment
    GET    /payments/summary — Payment summary
"""

from fastapi import APIRouter, HTTPException, Depends
from app.presentation.dependencies import get_tenant_context, require_admin
from app.domain.security.models import TenantContext
from pydantic import BaseModel
from typing import Optional, List

from app.domain.payment.service import get_payment_service
from app.domain.payment.models import PaymentStatus

router = APIRouter(prefix="/payments", tags=["payments"])


# ── Request/Response Schemas ─────────────────────────

class CreateMethodRequest(BaseModel):
    code: str
    name: str
    payment_type: str = "CUSTOM"
    display_order: int = 0
    requires_confirmation: bool = False
    description: str = ""
    fee_type: str = "NONE"
    fee_value: float = 0.0
    discount_type: str = "NONE"
    discount_value: float = 0.0

class UpdateMethodRequest(BaseModel):
    name: Optional[str] = None
    display_order: Optional[int] = None
    requires_confirmation: Optional[bool] = None
    description: Optional[str] = None
    fee_type: Optional[str] = None
    fee_value: Optional[float] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = None

class CreatePixRequest(BaseModel):
    key: str
    key_type: str = "RANDOM"
    holder_name: str = ""
    holder_document: str = ""
    institution: str = ""
    city: str = ""

class UpdatePixRequest(BaseModel):
    key: Optional[str] = None
    key_type: Optional[str] = None
    holder_name: Optional[str] = None
    holder_document: Optional[str] = None
    institution: Optional[str] = None
    city: Optional[str] = None

class CreatePaymentRequest(BaseModel):
    order_id: str
    order_codigo: str = ""
    customer_codigo: str = ""
    amount: float
    method_code: str

class ConfirmPaymentRequest(BaseModel):
    notes: str = ""


# ── Payment Methods ──────────────────────────────────

@router.get("/methods")
async def list_methods(ctx: TenantContext = Depends(get_tenant_context)):
    """List payment methods for current tenant."""
    service = get_payment_service()
    methods = service.get_methods(ctx.tenant_id)
    return {"methods": [m.to_dict() for m in methods], "count": len(methods)}


@router.post("/methods")
async def create_method(req: CreateMethodRequest,
                        ctx: TenantContext = Depends(require_admin)):
    """Create a payment method (admin only)."""
    service = get_payment_service()
    method = service.create_method(
        tenant_id=ctx.tenant_id,
        code=req.code,
        name=req.name,
        payment_type=req.payment_type,
        display_order=req.display_order,
        requires_confirmation=req.requires_confirmation,
        description=req.description,
        fee_type=req.fee_type,
        fee_value=req.fee_value,
        discount_type=req.discount_type,
        discount_value=req.discount_value,
    )
    return {"success": True, "method": method.to_dict()}


@router.patch("/methods/{method_id}")
async def update_method(method_id: str, req: UpdateMethodRequest,
                        ctx: TenantContext = Depends(require_admin)):
    """Update a payment method (admin only)."""
    service = get_payment_service()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    method = service.update_method(method_id, ctx.tenant_id, **updates)
    if not method:
        raise HTTPException(404, "Payment method not found")
    return {"success": True, "method": method.to_dict()}


@router.delete("/methods/{method_id}")
async def delete_method(method_id: str,
                        ctx: TenantContext = Depends(require_admin)):
    """Delete a payment method (admin only)."""
    service = get_payment_service()
    if not service.delete_method(method_id, ctx.tenant_id):
        raise HTTPException(404, "Payment method not found")
    return {"success": True}


@router.patch("/methods/{method_id}/toggle")
async def toggle_method(method_id: str,
                        ctx: TenantContext = Depends(require_admin)):
    """Enable/disable a payment method (admin only)."""
    service = get_payment_service()
    method = service.toggle_method(method_id, ctx.tenant_id)
    if not method:
        raise HTTPException(404, "Payment method not found")
    return {"success": True, "method": method.to_dict()}


# ── PIX Configuration ────────────────────────────────

@router.get("/pix")
async def get_pix(ctx: TenantContext = Depends(get_tenant_context)):
    """Get PIX configuration for current tenant."""
    service = get_payment_service()
    configs = service.get_pix_configs(ctx.tenant_id)
    return {"configs": [c.to_dict() for c in configs], "count": len(configs)}


@router.post("/pix")
async def create_pix(req: CreatePixRequest,
                     ctx: TenantContext = Depends(require_admin)):
    """Create PIX configuration (admin only)."""
    service = get_payment_service()
    config = service.create_pix_config(
        tenant_id=ctx.tenant_id,
        key=req.key,
        key_type=req.key_type,
        holder_name=req.holder_name,
        holder_document=req.holder_document,
        institution=req.institution,
        city=req.city,
    )
    return {"success": True, "config": config.to_dict()}


@router.patch("/pix/{config_id}")
async def update_pix(config_id: str, req: UpdatePixRequest,
                     ctx: TenantContext = Depends(require_admin)):
    """Update PIX configuration (admin only)."""
    service = get_payment_service()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    config = service.update_pix_config(config_id, ctx.tenant_id, **updates)
    if not config:
        raise HTTPException(404, "PIX configuration not found")
    return {"success": True, "config": config.to_dict()}


@router.delete("/pix/{config_id}")
async def delete_pix(config_id: str,
                     ctx: TenantContext = Depends(require_admin)):
    """Delete PIX configuration (admin only)."""
    service = get_payment_service()
    if not service.delete_pix_config(config_id, ctx.tenant_id):
        raise HTTPException(404, "PIX configuration not found")
    return {"success": True}


# ── Payments ─────────────────────────────────────────

@router.get("/")
async def list_payments(
    status: Optional[str] = None,
    limit: int = 50,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List payments for current tenant."""
    service = get_payment_service()
    payments = service.get_payments_for_tenant(ctx.tenant_id, status=status, limit=limit)
    return {"items": [p.to_dict() for p in payments], "count": len(payments)}


@router.post("/")
async def create_payment(req: CreatePaymentRequest,
                         ctx: TenantContext = Depends(get_tenant_context)):
    """Create a payment for an order."""
    service = get_payment_service()

    # Check for duplicate payment attempt
    existing = service.get_payments_for_order(req.order_id, ctx.tenant_id)
    for p in existing:
        if p.method_code == req.method_code and p.status == PaymentStatus.PENDING:
            return {"success": True, "payment": p.to_dict(), "duplicate": True}

    payment = service.create_payment(
        tenant_id=ctx.tenant_id,
        order_id=req.order_id,
        order_codigo=req.order_codigo,
        customer_codigo=req.customer_codigo,
        amount=req.amount,
        method_code=req.method_code,
    )
    return {"success": True, "payment": payment.to_dict()}


@router.get("/{payment_id}")
async def get_payment(payment_id: str,
                      ctx: TenantContext = Depends(get_tenant_context)):
    """Get payment detail."""
    service = get_payment_service()
    payment = service.get_payment(payment_id, ctx.tenant_id)
    if not payment:
        raise HTTPException(404, "Payment not found")
    return {"payment": payment.to_dict()}


@router.post("/{payment_id}/confirm")
async def confirm_payment(payment_id: str, req: ConfirmPaymentRequest,
                          ctx: TenantContext = Depends(get_tenant_context)):
    """Confirm a payment."""
    service = get_payment_service()
    payment = service.confirm_payment(payment_id, ctx.tenant_id,
                                       confirmed_by=ctx.user_id, notes=req.notes)
    if not payment:
        raise HTTPException(404, "Payment not found or cannot be confirmed")
    return {"success": True, "payment": payment.to_dict()}


@router.post("/{payment_id}/cancel")
async def cancel_payment(payment_id: str,
                         ctx: TenantContext = Depends(get_tenant_context)):
    """Cancel a payment."""
    service = get_payment_service()
    payment = service.cancel_payment(payment_id, ctx.tenant_id)
    if not payment:
        raise HTTPException(404, "Payment not found or cannot be cancelled")
    return {"success": True, "payment": payment.to_dict()}


@router.post("/{payment_id}/refund")
async def refund_payment(payment_id: str,
                         ctx: TenantContext = Depends(get_tenant_context)):
    """Refund a payment."""
    service = get_payment_service()
    payment = service.refund_payment(payment_id, ctx.tenant_id)
    if not payment:
        raise HTTPException(404, "Payment not found or cannot be refunded")
    return {"success": True, "payment": payment.to_dict()}


@router.get("/summary")
async def payment_summary(ctx: TenantContext = Depends(get_tenant_context)):
    """Get payment summary for dashboard."""
    service = get_payment_service()
    return service.get_payment_summary(ctx.tenant_id)
