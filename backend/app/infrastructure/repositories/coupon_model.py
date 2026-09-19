"""
Coupon SQLAlchemy Models — Módulo de Promoções e Cupons.

- coupons: definição do cupom (tipo, valor, condições, validade, limites).
- coupon_redemptions: resgates por pedido — dá o relatório de uso, o limite
  por cliente e a régua de um cupom por pedido (não acumulável).

F9.1: modelos em estilo SQLAlchemy 2.0 tipado (Mapped[...]) — atributos
instanciados em Python tipam como list/str/... em vez de Column[Any],
sem ignore no serviço.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class CouponModel(Base):
    __tablename__ = "coupons"

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_coupon_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, default="default", index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # PERCENTAGE | FIXED | FREE_SHIPPING
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[Optional[Any]] = mapped_column(Numeric(10, 2), nullable=True)  # 10.00 (R$) ou 15.0 (%)

    # Condições
    min_order_value: Mapped[Any] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    max_discount: Mapped[Optional[Any]] = mapped_column(Numeric(10, 2), nullable=True)  # cap do desconto percentual
    applicable_products: Mapped[Optional[list]] = mapped_column(
        JSON, default=list
    )  # lista de product_codigo ([] = todos)
    applicable_customers: Mapped[Optional[list]] = mapped_column(
        JSON, default=list
    )  # lista de client_codigo ([] = todos)

    # Validade
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Uso
    usage_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 = ilimitado
    usage_per_customer: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── Indicação (F4) ─────────────────────────────────
    # invite_token: identificador público do link de convite/auto-cadastro
    # (gerado on-demand; null em cupons comuns criados pelo admin).
    # is_referral: cupom nascido de uma indicação (não consome o 1/pedido
    # do cupom aplicado — validação do pedido continua no domain existente).
    invite_token: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True, index=True)
    is_referral: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CouponRedemptionModel(Base):
    __tablename__ = "coupon_redemptions"

    # Um cupom por pedido (não acumulável) — unique por pedido.
    __table_args__ = (UniqueConstraint("tenant_id", "order_codigo", name="uq_coupon_redemption_order"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, default="default", index=True, nullable=False)
    coupon_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    order_codigo: Mapped[str] = mapped_column(String, index=True, nullable=False)
    client_codigo: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    discount_amount: Mapped[Any] = mapped_column(Numeric(10, 2), nullable=False)
    # Economia de frete (FREE_SHIPPING) — para relatório e reversão correta.
    fee_saved: Mapped[Any] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    # Metadados para reverter corretamente ao remover o cupom:
    delivery_fee_before: Mapped[Any] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


# ── Indicações (F4): quem indicou quem e quais cupons a indicação gerou ──


class ReferralModel(Base):
    """Indicação: referrer convidou referred (auto-cadastro via token).

    Ambos recebem um cupom de mesmo valor (decisão G1 do spec). O limite
    mensal de indicações por cliente é validado no ReferralService.
    """

    __tablename__ = "referrals"

    __table_args__ = (UniqueConstraint("tenant_id", "invite_token", name="uq_referral_tenant_token"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, default="default", index=True, nullable=False)
    invite_token: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    referrer_client_codigo: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    referred_client_codigo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    # Cupons gerados (referrer + referred) — preenchidos no auto-cadastro
    referrer_coupon_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    referred_coupon_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    # Nome/telefone informados no cadastro (auditoria)
    referred_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    referred_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
