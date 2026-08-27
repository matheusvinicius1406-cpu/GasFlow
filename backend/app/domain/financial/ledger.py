"""
FinancialLedgerEntry Domain Entity — FASE 8

Immutable audit trail for important financial events.
NO UPDATE, NO DELETE. Corrections = new entry.
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional


class LedgerEventType(str, Enum):
    PAYMENT_CREATED = "PAYMENT_CREATED"
    PAYMENT_SETTLED = "PAYMENT_SETTLED"
    PAYMENT_REFUNDED = "PAYMENT_REFUNDED"
    EXPENSE_CREATED = "EXPENSE_CREATED"
    EXPENSE_CANCELLED = "EXPENSE_CANCELLED"
    RECEIVABLE_CREATED = "RECEIVABLE_CREATED"
    RECEIVABLE_SETTLED = "RECEIVABLE_SETTLED"
    CASH_INFLOW = "CASH_INFLOW"
    CASH_OUTFLOW = "CASH_OUTFLOW"


class FinancialLedgerEntry:
    def __init__(
        self,
        id: Optional[int] = None,
        event_type: LedgerEventType = LedgerEventType.PAYMENT_CREATED,
        amount: Decimal = Decimal("0.00"),
        reference_type: Optional[str] = None,  # "PAYMENT", "EXPENSE", "RECEIVABLE"
        reference_id: Optional[str] = None,
        description: str = "",
        created_at: Optional[datetime] = None,
    ):
        if isinstance(amount, float):
            amount = Decimal(str(amount))
        self.id = id
        self.event_type = event_type
        self.amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.reference_type = reference_type
        self.reference_id = reference_id
        self.description = description
        self.created_at = created_at or datetime.utcnow()

    def __repr__(self):
        return (
            f"LedgerEntry(event={self.event_type.value}, "
            f"amount=R${self.amount}, ref={self.reference_type}#{self.reference_id})"
        )
