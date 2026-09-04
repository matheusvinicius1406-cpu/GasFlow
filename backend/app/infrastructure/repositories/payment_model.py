"""
Payment Service Persistence Models — SQLAlchemy models.

Replaces in-memory PaymentService storage with database persistence.
Single source of truth for payment methods, PIX config, and payments.

Models:
- PaymentMethodRecord: payment_methods table
- PixConfigRecord: pix_configs table
- PaymentRecord: service_payments table (distinct from financial payments)
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Float, Text, Index, UniqueConstraint
)
from datetime import datetime
from app.infrastructure.database.base import Base


class PaymentMethodRecord(Base):
    """Persistent payment method — replaces in-memory _methods dict."""
    __tablename__ = "payment_methods"

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_payment_method_tenant_code"),
        Index("ix_payment_method_tenant", "tenant_id"),
    )

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String, default="default", nullable=False)
    code = Column(String(50), nullable=False)
    name = Column(String(100), nullable=False, default="")
    payment_type = Column(String(30), nullable=False, default="CUSTOM")
    enabled = Column(Boolean, default=True, nullable=False)
    display_order = Column(Integer, default=0, nullable=False)
    requires_confirmation = Column(Boolean, default=False, nullable=False)
    description = Column(Text, default="")
    fee_type = Column(String(20), default="NONE", nullable=False)
    fee_value = Column(Float, default=0.0, nullable=False)
    discount_type = Column(String(20), default="NONE", nullable=False)
    discount_value = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PixConfigRecord(Base):
    """Persistent PIX configuration — replaces in-memory _pix_configs dict."""
    __tablename__ = "pix_configs"

    __table_args__ = (
        Index("ix_pix_config_tenant", "tenant_id"),
    )

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String, default="default", nullable=False)
    key = Column(String(200), nullable=False, default="")
    key_type = Column(String(20), nullable=False, default="RANDOM")
    holder_name = Column(String(200), nullable=False, default="")
    holder_document = Column(String(20), nullable=False, default="")
    institution = Column(String(100), nullable=False, default="")
    city = Column(String(100), nullable=False, default="")
    copy_paste_code = Column(Text, default="")
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String, default="default", nullable=False)
    order_id = Column(String(36), nullable=False, default="")
    order_codigo = Column(String(50), nullable=False, default="")
    customer_codigo = Column(String(50), nullable=False, default="")
    amount = Column(Float, nullable=False, default=0.0)
    method_code = Column(String(50), nullable=False, default="")
    method_name = Column(String(100), nullable=False, default="")
    status = Column(String(20), nullable=False, default="PENDING")
    pix_key_used = Column(String(200), default="")
    pix_copy_paste = Column(Text, default="")
    confirmed_by = Column(String(100), default="")
    confirmed_at = Column(DateTime, nullable=True)
    confirmation_notes = Column(Text, default="")
    refunded_at = Column(DateTime, nullable=True)
    refund_reason = Column(Text, default="")
    provider = Column(String(50), default="")
    external_id = Column(String(100), default="")
    provider_status = Column(String(50), default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
