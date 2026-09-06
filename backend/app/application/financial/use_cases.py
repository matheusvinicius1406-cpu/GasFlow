"""
Financial Use Cases — FASE 8

Atomic transactions for all financial operations.
- RegisterPayment: create payment, update receivable, cash movement, ledger
- CreateReceivable: initial receivable from order
- RegisterExpense: expense + cash movement + ledger
- RefundPayment: reverse payment + cash movement
- FinancialReports: aggregated queries
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.domain.financial.payment import Payment, PaymentStatus, PaymentMethod
from app.domain.financial.receivable import Receivable, ReceivableStatus
from app.domain.financial.expense import Expense, ExpenseCategory
from app.domain.financial.cash_movement import CashMovement, CashMovementType
from app.domain.financial.ledger import FinancialLedgerEntry, LedgerEventType
from app.domain.financial.repository import (
    PaymentRepository,
    ReceivableRepository,
    ExpenseRepository,
    CashMovementRepository,
    FinancialLedgerRepository,
)
from app.domain.order.entity import PaymentStatus as OrderPaymentStatus
from app.domain.order.repository import OrderRepository


class RegisterPaymentUseCase:
    """Register a payment for an order. Atomic: payment + receivable + cash + ledger + order status."""

    def __init__(
        self,
        payment_repo: PaymentRepository,
        receivable_repo: ReceivableRepository,
        cash_repo: CashMovementRepository,
        ledger_repo: FinancialLedgerRepository,
        order_repo: Optional[OrderRepository] = None,
    ):
        self.payment_repo = payment_repo
        self.receivable_repo = receivable_repo
        self.cash_repo = cash_repo
        self.ledger_repo = ledger_repo
        self.order_repo = order_repo

    def execute(self, data: dict) -> dict:
        order_codigo = data["order_codigo"]
        amount = Decimal(str(data["amount"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        method = PaymentMethod(data.get("method", "CASH"))
        idempotency_key = data.get("idempotency_key")
        reference = data.get("reference")
        notes = data.get("notes")

        if amount <= 0:
            raise ValueError("Payment amount must be > 0")

        # 1. Idempotency check
        if idempotency_key and self.payment_repo.exists_by_idempotency_key(idempotency_key):
            existing = self.payment_repo.get_by_idempotency_key(idempotency_key)
            return {"payment": existing, "status": "already_exists"}

        # 2. Get or create receivable
        receivable = self.receivable_repo.get_by_order(order_codigo)
        if not receivable:
            raise ValueError(f"No receivable found for order {order_codigo}")

        if receivable.status in (ReceivableStatus.PAID, ReceivableStatus.CANCELLED):
            raise ValueError(f"Order {order_codigo} is already {receivable.status.value}")

        # 3. Check overpayment
        if amount > receivable.remaining_amount:
            raise ValueError(f"Payment R${amount} exceeds remaining R${receivable.remaining_amount}")

        # 4. Create payment
        now = datetime.utcnow()
        payment = Payment(
            order_codigo=order_codigo,
            amount=amount,
            method=method,
            status=PaymentStatus.PAID,
            paid_at=now,
            reference=reference,
            idempotency_key=idempotency_key,
            notes=notes,
            created_at=now,
        )
        payment = self.payment_repo.create(payment)

        # 5. Update receivable
        new_paid = receivable.paid_amount + amount
        new_status = ReceivableStatus.PAID if new_paid >= receivable.original_amount else ReceivableStatus.PARTIAL
        receivable.paid_amount = new_paid.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        receivable.status = new_status
        if new_status == ReceivableStatus.PAID:
            receivable.settled_at = now
        receivable = self.receivable_repo.update(receivable)

        # 6. Sync order.payment_status
        if self.order_repo:
            order = self.order_repo.buscar_por_codigo(order_codigo)
            if order:
                if new_paid >= receivable.original_amount:
                    order.payment_status = OrderPaymentStatus.PAID
                elif new_paid > 0:
                    order.payment_status = OrderPaymentStatus.PARTIAL
                order.updated_at = now
                self.order_repo.criar(order)  # _to_model handles update via entity.id

        # 7. Cash movement (receipt)
        current_balance = self.cash_repo.current_balance()
        new_balance = current_balance + amount
        cash_movement = CashMovement(
            type=CashMovementType.RECEIPT,
            amount=amount,
            description=f"Payment for Order #{order_codigo}",
            reference_type="PAYMENT",
            reference_id=str(payment.id),
            balance_after=new_balance.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            created_at=now,
        )
        cash_movement = self.cash_repo.create(cash_movement)

        # 8. Ledger entry
        ledger_entry = FinancialLedgerEntry(
            event_type=LedgerEventType.PAYMENT_CREATED,
            amount=amount,
            reference_type="PAYMENT",
            reference_id=str(payment.id),
            description=f"Payment R${amount} for Order #{order_codigo} via {method.value}",
            created_at=now,
        )
        self.ledger_repo.create(ledger_entry)

        return {
            "payment": payment,
            "receivable": receivable,
            "cash_movement": cash_movement,
            "status": "created",
        }


class CreateReceivableUseCase:
    """Create receivable when order is confirmed."""

    def __init__(self, receivable_repo: ReceivableRepository, ledger_repo: FinancialLedgerRepository):
        self.receivable_repo = receivable_repo
        self.ledger_repo = ledger_repo

    def execute(
        self, order_codigo: str, customer_codigo: str, total: Decimal, due_date: Optional[datetime] = None
    ) -> Receivable:
        # Check if receivable already exists
        existing = self.receivable_repo.get_by_order(order_codigo)
        if existing:
            return existing

        receivable = Receivable(
            customer_codigo=customer_codigo,
            order_codigo=order_codigo,
            original_amount=total,
            paid_amount=Decimal("0.00"),
            due_date=due_date,
            status=ReceivableStatus.OPEN,
        )
        receivable = self.receivable_repo.create(receivable)

        # Ledger
        self.ledger_repo.create(
            FinancialLedgerEntry(
                event_type=LedgerEventType.RECEIVABLE_CREATED,
                amount=total,
                reference_type="RECEIVABLE",
                reference_id=str(receivable.id),
                description=f"Receivable R${total} for Order #{order_codigo}",
            )
        )

        return receivable


class RegisterExpenseUseCase:
    """Register an expense. Atomic: expense + cash movement + ledger."""

    def __init__(
        self, expense_repo: ExpenseRepository, cash_repo: CashMovementRepository, ledger_repo: FinancialLedgerRepository
    ):
        self.expense_repo = expense_repo
        self.cash_repo = cash_repo
        self.ledger_repo = ledger_repo

    def execute(self, data: dict) -> dict:
        amount = Decimal(str(data["amount"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if amount <= 0:
            raise ValueError("Expense amount must be > 0")

        now = datetime.utcnow()
        expense = Expense(
            description=data["description"],
            amount=amount,
            category=ExpenseCategory(data.get("category", "OTHER")),
            date=data.get("date", now),
            payment_method=data.get("payment_method"),
            notes=data.get("notes"),
            created_at=now,
        )
        expense = self.expense_repo.create(expense)

        # Cash movement (outflow)
        current_balance = self.cash_repo.current_balance()
        new_balance = current_balance - amount
        cash_movement = CashMovement(
            type=CashMovementType.EXPENSE,
            amount=amount,
            description=f"Expense: {expense.description}",
            reference_type="EXPENSE",
            reference_id=str(expense.id),
            balance_after=new_balance.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            created_at=now,
        )
        cash_movement = self.cash_repo.create(cash_movement)

        # Ledger
        self.ledger_repo.create(
            FinancialLedgerEntry(
                event_type=LedgerEventType.EXPENSE_CREATED,
                amount=amount,
                reference_type="EXPENSE",
                reference_id=str(expense.id),
                description=f"Expense R${amount}: {expense.description}",
                created_at=now,
            )
        )

        return {"expense": expense, "cash_movement": cash_movement}


class RefundPaymentUseCase:
    """Refund a payment. Atomic: refund payment + cash movement + ledger."""

    def __init__(
        self,
        payment_repo: PaymentRepository,
        receivable_repo: ReceivableRepository,
        cash_repo: CashMovementRepository,
        ledger_repo: FinancialLedgerRepository,
    ):
        self.payment_repo = payment_repo
        self.receivable_repo = receivable_repo
        self.cash_repo = cash_repo
        self.ledger_repo = ledger_repo

    def execute(self, payment_id: int, reason: str = "") -> dict:
        payment = self.payment_repo.get_by_id(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")
        if payment.status == PaymentStatus.REFUNDED:
            return {"payment": payment, "status": "already_refunded"}

        # Mark payment as refunded
        notes = f"REFUNDED: {reason}" if reason else "REFUNDED"
        payment = self.payment_repo.update_status(payment.id, PaymentStatus.REFUNDED, notes=notes)

        # Update receivable
        receivable = self.receivable_repo.get_by_order(payment.order_codigo)
        if receivable:
            new_paid = max(Decimal("0.00"), receivable.paid_amount - payment.amount)
            receivable.paid_amount = new_paid.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            receivable.status = (
                ReceivableStatus.PAID
                if new_paid >= receivable.original_amount
                else ReceivableStatus.PARTIAL
                if new_paid > 0
                else ReceivableStatus.OPEN
            )
            self.receivable_repo.update(receivable)

        # Cash movement (refund outflow)
        current_balance = self.cash_repo.current_balance()
        new_balance = current_balance - payment.amount
        cash_movement = CashMovement(
            type=CashMovementType.REFUND,
            amount=payment.amount,
            description=f"Refund for Order #{payment.order_codigo}",
            reference_type="REFUND",
            reference_id=str(payment.id),
            balance_after=new_balance.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )
        cash_movement = self.cash_repo.create(cash_movement)

        # Ledger
        self.ledger_repo.create(
            FinancialLedgerEntry(
                event_type=LedgerEventType.PAYMENT_REFUNDED,
                amount=payment.amount,
                reference_type="PAYMENT",
                reference_id=str(payment.id),
                description=f"Refund R${payment.amount} for Order #{payment.order_codigo}",
            )
        )

        return {"payment": payment, "cash_movement": cash_movement}


class FinancialReportsUseCase:
    """Basic financial reports for a period."""

    def __init__(
        self,
        payment_repo: PaymentRepository,
        receivable_repo: ReceivableRepository,
        expense_repo: ExpenseRepository,
        cash_repo: CashMovementRepository,
    ):
        self.payment_repo = payment_repo
        self.receivable_repo = receivable_repo
        self.expense_repo = expense_repo
        self.cash_repo = cash_repo

    def daily_summary(self, date: datetime) -> dict:
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(day=start.day + 1) if start.day < 28 else start.replace(month=start.month + 1, day=1)

        total_receipts = self.cash_repo.total_by_type_and_period(CashMovementType.RECEIPT, start, end)
        total_expenses = self.expense_repo.total_by_period(start, end)

        return {
            "date": start.isoformat(),
            "total_receipts": total_receipts,
            "total_expenses": total_expenses,
            "net_result": (total_receipts - total_expenses).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        }
