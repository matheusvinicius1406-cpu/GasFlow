"""
Coupon domain — tipos, validação e cálculo de desconto (puro, sem I/O).

Regras de negócio (prompt Fase 2):
- Cupom ativo e dentro da validade.
- Pedido atende min_order_value.
- Produtos aplicáveis presentes no pedido (se restrito).
- Cliente aplicável no pedido (se restrito).
- Limites de uso: global (usage_limit) e por cliente (usage_per_customer).
- Não acumulável (um cupom por pedido — garantido por constraint no resgate).
- Cálculo:
    PERCENTAGE  → subtotal * value/100, respeitando max_discount.
    FIXED       → min(value, total elegível).
    FREE_SHIPPING → zera o frete (desconto = delivery_fee).
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional


def money(v) -> Decimal:
    """Arredonda para centavos (padrão financeiro)."""
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CouponType:
    PERCENTAGE = "PERCENTAGE"
    FIXED = "FIXED"
    FREE_SHIPPING = "FREE_SHIPPING"

    ALL = (PERCENTAGE, FIXED, FREE_SHIPPING)


class CouponValidationError(Exception):
    """Cupom inválido para o contexto informado. `code` é estável p/ i18n/API."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class CouponSnapshot:
    """Visão imutável do cupom para validação/cálculo (sem ORM)."""

    id: str
    code: str
    type: str
    value: Optional[Decimal]
    min_order_value: Decimal
    max_discount: Optional[Decimal]
    applicable_products: List[str]
    applicable_customers: List[str]
    start_date: datetime
    end_date: datetime
    usage_limit: int  # 0 = ilimitado
    usage_per_customer: int
    usage_count: int
    is_active: bool = True

    @classmethod
    def from_model(cls, m) -> "CouponSnapshot":
        return cls(
            id=m.id,
            code=m.code,
            type=m.type,
            value=Decimal(str(m.value)) if m.value is not None else None,
            min_order_value=Decimal(str(m.min_order_value or 0)),
            max_discount=Decimal(str(m.max_discount)) if m.max_discount is not None else None,
            applicable_products=list(m.applicable_products or []),
            applicable_customers=list(m.applicable_customers or []),
            start_date=m.start_date,
            end_date=m.end_date,
            usage_limit=m.usage_limit or 0,
            usage_per_customer=m.usage_per_customer or 1,
            usage_count=m.usage_count or 0,
            is_active=bool(m.is_active),
        )


@dataclass
class OrderContext:
    """Contexto mínimo do pedido para validar/aplicar o cupom."""

    subtotal: Decimal
    delivery_fee: Decimal
    product_codigos: List[str]
    client_codigo: Optional[str] = None
    now: Optional[datetime] = None
    customer_usage_count: int = 0  # resgates anteriores deste cliente neste cupom

    @property
    def total(self) -> Decimal:
        return money(self.subtotal + self.delivery_fee)


@dataclass
class CouponApplication:
    """Resultado da aplicação — valores em centavos (Decimal 2 casas).

    discount_amount: quanto entra na coluna `discount` do pedido.
    fee_saved: economia de frete (FREE_SHIPPING) — não entra em `discount`.
    """

    discount_amount: Decimal
    fee_saved: Decimal
    new_delivery_fee: Decimal
    new_total: Decimal


def validate_coupon(coupon: CouponSnapshot, ctx: OrderContext) -> None:
    """Valida o cupom contra o contexto. Levanta CouponValidationError se inválido."""
    now = ctx.now or datetime.utcnow()

    if not coupon.is_active:
        raise CouponValidationError("INACTIVE", "Cupom inativo.")
    if now < coupon.start_date:
        raise CouponValidationError("NOT_STARTED", "Cupom ainda não está válido.")
    if now > coupon.end_date:
        raise CouponValidationError("EXPIRED", "Cupom expirado.")

    if coupon.usage_limit and coupon.usage_count >= coupon.usage_limit:
        raise CouponValidationError("USAGE_LIMIT", "Limite de usos do cupom atingido.")

    if ctx.customer_usage_count >= coupon.usage_per_customer:
        raise CouponValidationError("PER_CUSTOMER_LIMIT", "Limite de uso por cliente atingido.")

    # Restrição de produtos: o pedido deve conter ao menos um produto aplicável.
    if coupon.applicable_products and not any(p in ctx.product_codigos for p in coupon.applicable_products):
        raise CouponValidationError("PRODUCT_NOT_ALLOWED", "Cupom não aplicável aos produtos do pedido.")

    # Restrição de clientes.
    if coupon.applicable_customers and ctx.client_codigo not in coupon.applicable_customers:
        raise CouponValidationError("CUSTOMER_NOT_ALLOWED", "Cupom não aplicável a este cliente.")

    if ctx.subtotal < coupon.min_order_value:
        raise CouponValidationError(
            "MIN_ORDER_VALUE",
            f"Pedido mínimo de R$ {coupon.min_order_value} para este cupom.",
        )


def calculate_discount(coupon: CouponSnapshot, ctx: OrderContext) -> CouponApplication:
    """Valida e calcula o desconto. Levanta CouponValidationError se inválido."""
    validate_coupon(coupon, ctx)

    if coupon.type == CouponType.PERCENTAGE:
        raw = ctx.subtotal * (coupon.value or Decimal("0")) / Decimal("100")
        if coupon.max_discount is not None:
            raw = min(raw, coupon.max_discount)
        discount = money(min(raw, ctx.subtotal))
        new_fee = ctx.delivery_fee
        fee_saved = Decimal("0.00")

    elif coupon.type == CouponType.FIXED:
        discount = money(min(coupon.value or Decimal("0"), ctx.subtotal + ctx.delivery_fee))
        new_fee = ctx.delivery_fee
        fee_saved = Decimal("0.00")

    elif coupon.type == CouponType.FREE_SHIPPING:
        # O frete é zerado; NÃO entra na coluna discount (evita descontar 2x).
        discount = Decimal("0.00")
        fee_saved = money(ctx.delivery_fee)
        new_fee = Decimal("0.00")

    else:
        raise CouponValidationError("INVALID_TYPE", "Tipo de cupom desconhecido.")

    new_total = money(ctx.subtotal + new_fee - discount)
    return CouponApplication(
        discount_amount=discount, fee_saved=fee_saved, new_delivery_fee=new_fee, new_total=new_total
    )
