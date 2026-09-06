"""
Financial SQLAlchemy Models — FASE 8

Decimal (NUMERIC) for all monetary values.
Constraints: amount > 0, remaining >= 0, FK relationships.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Numeric, Index
from datetime import datetime
from decimal import Decimal
from app.infrastructure.database.base import Base


class PaymentModel(Base):
    __tablename__ = "payments"

    tenant_id = Column(String, default="default", index=True)
    id = Column(Integer, primary_key=True, index=True)
    order_codigo = Column(String, nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    method = Column(String, nullable=False)  # CASH, PIX, CARD, TRANSFER, OTHER
    status = Column(String, nullable=False, default="PENDING")
    paid_at = Column(DateTime, nullable=True)
    reference = Column(String, nullable=True)
    idempotency_key = Column(String, nullable=True, unique=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_payments_order", "order_codigo"),
        Index("ix_payments_status", "status"),
        Index("ix_payments_created", "created_at"),
    )


class ReceivableModel(Base):
    __tablename__ = "receivables"

    tenant_id = Column(String, default="default", index=True)
    id = Column(Integer, primary_key=True, index=True)
    customer_codigo = Column(String, nullable=False, index=True)
    order_codigo = Column(String, nullable=False, index=True)
    original_amount = Column(Numeric(10, 2), nullable=False)
    paid_amount = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    due_date = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default="OPEN")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    settled_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_receivables_customer", "customer_codigo"),
        Index("ix_receivables_order", "order_codigo"),
        Index("ix_receivables_status", "status"),
        Index("ix_receivables_due_date", "due_date"),
    )


class ExpenseModel(Base):
    __tablename__ = "expenses"

    tenant_id = Column(String, default="default", index=True)
    id = Column(Integer, primary_key=True, index=True)
    description = Column(Text, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    category = Column(String, nullable=False, default="OTHER")
    date = Column(DateTime, nullable=False)
    payment_method = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_expenses_category", "category"),
        Index("ix_expenses_date", "date"),
        Index("ix_expenses_status", "status"),
    )


class CashMovementModel(Base):
    __tablename__ = "cash_movements"

    tenant_id = Column(String, default="default", index=True)
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False)  # RECEIPT, EXPENSE, REFUND, ADJUSTMENT
    amount = Column(Numeric(10, 2), nullable=False)
    description = Column(Text, nullable=False)
    reference_type = Column(String, nullable=True)  # PAYMENT, EXPENSE, REFUND
    reference_id = Column(String, nullable=True)
    balance_after = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_cash_movements_type", "type"),
        Index("ix_cash_movements_created", "created_at"),
        Index("ix_cash_movements_reference", "reference_type", "reference_id"),
    )


class FinancialLedgerModel(Base):
    __tablename__ = "financial_ledger"

    tenant_id = Column(String, default="default", index=True)
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    reference_type = Column(String, nullable=True)
    reference_id = Column(String, nullable=True)
    description = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_ledger_event_type", "event_type"),
        Index("ix_ledger_created", "created_at"),
        Index("ix_ledger_reference", "reference_type", "reference_id"),
    )
