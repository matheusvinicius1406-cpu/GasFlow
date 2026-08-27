"""
Payment Domain Entity — FASE 8

Payment = effeclitely registered payment for an Order.
Decimal money model. Immutable after creation (except status transitions).
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PaymentMethod(str, Enum):
    CASH = "CASH"
    PIX = "PIX"
    CARD = "CARD"
    TRANSFER = "TRANSFER"
    OTHER = "OTHER"


class Payment:
    def __init__(
        self,
        id: Optional[int] = None,
        order_codigo: str = "",
        amount: Decimal = Decimal("0.00"),
        method: PaymentMethod = PaymentMethod.CASH,
        status: PaymentStatus = PaymentStatus.PENDING,
        paid_at: Optional[datetime] = None,
        reference: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        notes: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ):
        if isinstance(amount, float):
            amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero")
        self.id = id
        self.order_codigo = order_codigo
        self.amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.method = method
        self.status = status
        self.paid_at = paid_at
        self.reference = reference
        self.idempotency_key = idempotency_key
        self.notes = notes
        self.created_at = created_at or datetime.utcnow()

    def __repr__(self):
        return (
            f"Payment(order={self.order_codigo}, "
            f"amount=R${self.amount}, method={self.method.value}, "
            f"status={self.status.value})"
        )
