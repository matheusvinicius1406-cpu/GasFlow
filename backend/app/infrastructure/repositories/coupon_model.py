"""
Coupon SQLAlchemy Models — Módulo de Promoções e Cupons.

- coupons: definição do cupom (tipo, valor, condições, validade, limites).
- coupon_redemptions: resgates por pedido — dá o relatório de uso, o limite
  por cliente e a régua de um cupom por pedido (não acumulável).
"""

from sqlalchemy import (
    Column,
    String,
    Numeric,
    Integer,
    DateTime,
    Boolean,
    JSON,
    UniqueConstraint,
)
from datetime import datetime
from app.infrastructure.database.base import Base


class CouponModel(Base):
    __tablename__ = "coupons"

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_coupon_tenant_code"),)

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String, default="default", index=True, nullable=False)
    code = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=True)
    description = Column(String(255), nullable=True)

    # PERCENTAGE | FIXED | FREE_SHIPPING
    type = Column(String(20), nullable=False)
    value = Column(Numeric(10, 2), nullable=True)  # 10.00 (R$) ou 15.0 (%)

    # Condições
    min_order_value = Column(Numeric(10, 2), default=0, nullable=False)
    max_discount = Column(Numeric(10, 2), nullable=True)  # cap do desconto percentual
    applicable_products = Column(JSON, default=list)  # lista de product_codigo ([] = todos)
    applicable_customers = Column(JSON, default=list)  # lista de client_codigo ([] = todos)

    # Validade
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)

    # Uso
    usage_limit = Column(Integer, default=0, nullable=False)  # 0 = ilimitado
    usage_per_customer = Column(Integer, default=1, nullable=False)
    usage_count = Column(Integer, default=0, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CouponRedemptionModel(Base):
    __tablename__ = "coupon_redemptions"

    # Um cupom por pedido (não acumulável) — unique por pedido.
    __table_args__ = (UniqueConstraint("tenant_id", "order_codigo", name="uq_coupon_redemption_order"),)

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String, default="default", index=True, nullable=False)
    coupon_id = Column(String(36), index=True, nullable=False)
    order_codigo = Column(String, index=True, nullable=False)
    client_codigo = Column(String, nullable=True)
    discount_amount = Column(Numeric(10, 2), nullable=False)
    # Economia de frete (FREE_SHIPPING) — para relatório e reversão correta.
    fee_saved = Column(Numeric(10, 2), default=0, nullable=False)
    # Metadados para reverter corretamente ao remover o cupom:
    delivery_fee_before = Column(Numeric(10, 2), default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
