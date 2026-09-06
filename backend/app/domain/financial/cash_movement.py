"""
CashMovement Domain Entity — FASE 8

CashMovement = cash inflow/outflow record. Immutable ledger entry.
Balance is DERIVED, never sent by frontend.
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional


class CashMovementType(str, Enum):
    RECEIPT = "RECEIPT"  # Money received (payment from customer)
    EXPENSE = "EXPENSE"  # Money paid out (operational cost)
    REFUND = "REFUND"  # Money returned to customer
    ADJUSTMENT = "ADJUSTMENT"  # Manual correction


class CashMovement:
    def __init__(
        self,
        id: Optional[int] = None,
        type: CashMovementType = CashMovementType.RECEIPT,
        amount: Decimal = Decimal("0.00"),
        description: str = "",
        reference_type: Optional[str] = None,  # "PAYMENT", "EXPENSE", "REFUND"
        reference_id: Optional[str] = None,  # payment.id, expense.id
        balance_after: Decimal = Decimal("0.00"),
        created_at: Optional[datetime] = None,
    ):
        if isinstance(amount, float):
            amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError("CashMovement amount must be > 0")
        if isinstance(balance_after, float):
            balance_after = Decimal(str(balance_after))

        self.id = id
        self.type = type
        self.amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.description = description
        self.reference_type = reference_type
        self.reference_id = reference_id
        self.balance_after = balance_after.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.created_at = created_at or datetime.utcnow()

    def __repr__(self):
        return f"CashMovement(type={self.type.value}, amount=R${self.amount}, " f"balance_after=R${self.balance_after})"
