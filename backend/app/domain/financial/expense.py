"""
Expense Domain Entity — FASE 8

Expense = operational cost记录. Immutable after creation.
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional


class ExpenseCategory(str, Enum):
    FUEL = "FUEL"
    MAINTENANCE = "MAINTENANCE"
    SUPPLIES = "SUPPLIES"
    UTILITIES = "UTILITIES"
    SALARY = "SALARY"
    TAX = "TAX"
    OTHER = "OTHER"


class ExpenseStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"


class Expense:
    def __init__(
        self,
        id: Optional[int] = None,
        description: str = "",
        amount: Decimal = Decimal("0.00"),
        category: ExpenseCategory = ExpenseCategory.OTHER,
        date: Optional[datetime] = None,
        payment_method: Optional[str] = None,
        notes: Optional[str] = None,
        status: ExpenseStatus = ExpenseStatus.ACTIVE,
        created_at: Optional[datetime] = None,
    ):
        if isinstance(amount, float):
            amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError("Expense amount must be > 0")
        self.id = id
        self.description = description
        self.amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.category = category
        self.date = date or datetime.utcnow()
        self.payment_method = payment_method
        self.notes = notes
        self.status = status
        self.created_at = created_at or datetime.utcnow()

    def __repr__(self):
        return (
            f"Expense(desc={self.description}, amount=R${self.amount}, "
            f"category={self.category.value}, status={self.status.value})"
        )
