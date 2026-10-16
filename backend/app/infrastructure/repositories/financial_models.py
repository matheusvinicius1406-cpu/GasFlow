"""
Financial SQLAlchemy Models — FASE 8

Decimal (NUMERIC) for all monetary values.
Constraints: amount > 0, remaining >= 0, FK relationships.

Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): colunas Numeric ficam como
`Any` (mesma convenção do `coupon_model.py`) e a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class PaymentModel(Base):
    __tablename__ = "payments"

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_codigo: Mapped[str] = mapped_column(String, nullable=False, index=True)
    amount: Mapped[Any] = mapped_column(Numeric(10, 2), nullable=False)
    method: Mapped[str] = mapped_column(String, nullable=False)  # CASH, PIX, CARD, TRANSFER, OTHER
    status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING")
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_payments_order", "order_codigo"),
        Index("ix_payments_status", "status"),
        Index("ix_payments_created", "created_at"),
    )


class ReceivableModel(Base):
    __tablename__ = "receivables"

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_codigo: Mapped[str] = mapped_column(String, nullable=False, index=True)
    order_codigo: Mapped[str] = mapped_column(String, nullable=False, index=True)
    original_amount: Mapped[Any] = mapped_column(Numeric(10, 2), nullable=False)
    paid_amount: Mapped[Any] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_receivables_customer", "customer_codigo"),
        Index("ix_receivables_order", "order_codigo"),
        Index("ix_receivables_status", "status"),
        Index("ix_receivables_due_date", "due_date"),
    )


class ExpenseModel(Base):
    __tablename__ = "expenses"

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Any] = mapped_column(Numeric(10, 2), nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False, default="OTHER")
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    payment_method: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_expenses_category", "category"),
        Index("ix_expenses_date", "date"),
        Index("ix_expenses_status", "status"),
    )


class CashMovementModel(Base):
    __tablename__ = "cash_movements"

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)  # RECEIPT, EXPENSE, REFUND, ADJUSTMENT
    amount: Mapped[Any] = mapped_column(Numeric(10, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reference_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # PAYMENT, EXPENSE, REFUND
    reference_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    balance_after: Mapped[Any] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_cash_movements_type", "type"),
        Index("ix_cash_movements_created", "created_at"),
        Index("ix_cash_movements_reference", "reference_type", "reference_id"),
    )


class FinancialLedgerModel(Base):
    __tablename__ = "financial_ledger"

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Any] = mapped_column(Numeric(10, 2), nullable=False)
    reference_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reference_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_ledger_event_type", "event_type"),
        Index("ix_ledger_created", "created_at"),
        Index("ix_ledger_reference", "reference_type", "reference_id"),
    )


class FinanceBudgetModel(Base):
    """Orçamento mensal por categoria — V4 (tenant, ano, mês, categoria)."""

    __tablename__ = "finance_budgets"

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–12
    category: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Any] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "year", "month", "category", name="uq_finance_budgets_period"),
        Index("ix_finance_budgets_period", "year", "month"),
    )


class FinanceSavedReportModel(Base):
    """Relatório salvo pelo usuário (Central Financeira)."""

    __tablename__ = "finance_saved_reports"

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    report_type: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_finance_saved_reports_name"),
        Index("ix_finance_saved_reports_created", "created_at"),
    )
