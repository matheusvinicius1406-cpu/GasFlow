"""
Receivable Domain Entity — FASE 8

Receivable = financial obligation for unpaid/partially-paid orders.
Derived from Payment events. Immutable ledger entry.
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional


class ReceivableStatus(str, Enum):
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class Receivable:
    def __init__(
        self,
        id: Optional[int] = None,
        customer_codigo: str = "",
        order_codigo: str = "",
        original_amount: Decimal = Decimal("0.00"),
        paid_amount: Decimal = Decimal("0.00"),
        due_date: Optional[datetime] = None,
        status: ReceivableStatus = ReceivableStatus.OPEN,
        created_at: Optional[datetime] = None,
        settled_at: Optional[datetime] = None,
    ):
        if isinstance(original_amount, float):
            original_amount = Decimal(str(original_amount))
        if isinstance(paid_amount, float):
            paid_amount = Decimal(str(paid_amount))
        if original_amount <= 0:
            raise ValueError("Receivable original_amount must be > 0")
        if paid_amount < 0:
            raise ValueError("Receivable paid_amount cannot be negative")

        self.id = id
        self.customer_codigo = customer_codigo
        self.order_codigo = order_codigo
        self.original_amount = original_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.paid_amount = paid_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.due_date = due_date
        self.status = status
        self.created_at = created_at or datetime.utcnow()
        self.settled_at = settled_at

    @property
    def remaining_amount(self) -> Decimal:
        remaining = self.original_amount - self.paid_amount
        return remaining.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def __repr__(self):
        return (
            f"Receivable(order={self.order_codigo}, "
            f"original=R${self.original_amount}, paid=R${self.paid_amount}, "
            f"remaining=R${self.remaining_amount}, status={self.status.value})"
        )
