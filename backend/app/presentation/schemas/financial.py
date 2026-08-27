"""
Financial Pydantic Schemas — FASE 8

Frontend CANNOT send: remaining_amount, paid_amount, cash_balance, balance_after.
Backend calculates all derived values.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field


# ── Payment ──────────────────────────────────────────

class PaymentCreate(BaseModel):
    order_codigo: str
    amount: Decimal = Field(..., gt=0, description="Payment amount > 0")
    method: str = Field("CASH", description="CASH, PIX, CARD, TRANSFER, OTHER")
    reference: Optional[str] = None
    idempotency_key: Optional[str] = None
    notes: Optional[str] = None


class PaymentResponse(BaseModel):
    id: int
    order_codigo: str
    amount: Decimal
    method: str
    status: str
    paid_at: Optional[datetime] = None
    reference: Optional[str] = None
    idempotency_key: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Receivable ───────────────────────────────────────

class ReceivableResponse(BaseModel):
    id: int
    customer_codigo: str
    order_codigo: str
    original_amount: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal = Field(description="Derived: original - paid")
    due_date: Optional[datetime] = None
    status: str
    created_at: datetime
    settled_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Expense ──────────────────────────────────────────

class ExpenseCreate(BaseModel):
    description: str = Field(..., min_length=1)
    amount: Decimal = Field(..., gt=0, description="Expense amount > 0")
    category: str = Field("OTHER")
    date: Optional[datetime] = None
    payment_method: Optional[str] = None
    notes: Optional[str] = None


class ExpenseResponse(BaseModel):
    id: int
    description: str
    amount: Decimal
    category: str
    date: datetime
    payment_method: Optional[str] = None
    notes: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Cash Movement ────────────────────────────────────

class CashMovementResponse(BaseModel):
    id: int
    type: str
    amount: Decimal
    description: str
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    balance_after: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


# ── Financial Reports ────────────────────────────────

class DailySummaryResponse(BaseModel):
    date: str
    total_receipts: Decimal
    total_expenses: Decimal
    net_result: Decimal


# ── Paginated responses ─────────────────────────────

class PaymentListResponse(BaseModel):
    items: List[PaymentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ReceivableListResponse(BaseModel):
    items: List[ReceivableResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ExpenseListResponse(BaseModel):
    items: List[ExpenseResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CashMovementListResponse(BaseModel):
    items: List[CashMovementResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
