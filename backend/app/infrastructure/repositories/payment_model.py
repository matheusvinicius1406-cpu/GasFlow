"""
Payment Service Persistence Models — SQLAlchemy models.

Replaces in-memory PaymentService storage with database persistence.
Single source of truth for payment methods, PIX config, and payments.

Models:
- PaymentMethodRecord: payment_methods table
- PixConfigRecord: pix_configs table
- PaymentServiceRecord: service_payments table (distinct from financial payments)

Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class PaymentMethodRecord(Base):
    """Persistent payment method — replaces in-memory _methods dict."""

    __tablename__ = "payment_methods"

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_payment_method_tenant_code"),
        Index("ix_payment_method_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, default="default", nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    payment_type: Mapped[str] = mapped_column(String(30), nullable=False, default="CUSTOM")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, default="")
    fee_type: Mapped[str] = mapped_column(String(20), default="NONE", nullable=False)
    fee_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    discount_type: Mapped[str] = mapped_column(String(20), default="NONE", nullable=False)
    discount_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PixConfigRecord(Base):
    """Persistent PIX configuration — replaces in-memory _pix_configs dict."""

    __tablename__ = "pix_configs"

    __table_args__ = (Index("ix_pix_config_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, default="default", nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    key_type: Mapped[str] = mapped_column(String(20), nullable=False, default="RANDOM")
    holder_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    holder_document: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    institution: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    city: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    copy_paste_code: Mapped[Optional[str]] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PaymentServiceRecord(Base):
    """Persistent payment record from PaymentService — replaces in-memory _payments dict.

    Note: This is distinct from the financial PaymentModel which tracks
    accounting entries. This tracks the PaymentService domain lifecycle.
    """

    __tablename__ = "service_payments"

    __table_args__ = (
        Index("ix_service_payment_tenant", "tenant_id"),
        Index("ix_service_payment_order", "order_id"),
        Index("ix_service_payment_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, default="default", nullable=False)
    order_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    order_codigo: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    customer_codigo: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    method_code: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    method_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    pix_key_used: Mapped[Optional[str]] = mapped_column(String(200), default="")
    pix_copy_paste: Mapped[Optional[str]] = mapped_column(Text, default="")
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(100), default="")
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    confirmation_notes: Mapped[Optional[str]] = mapped_column(Text, default="")
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    refund_reason: Mapped[Optional[str]] = mapped_column(Text, default="")
    provider: Mapped[Optional[str]] = mapped_column(String(50), default="")
    external_id: Mapped[Optional[str]] = mapped_column(String(100), default="")
    provider_status: Mapped[Optional[str]] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
