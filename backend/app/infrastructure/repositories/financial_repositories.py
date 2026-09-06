"""
Financial Repository Implementations — FASE 8

All monetary values stored/returned as Decimal.
Atomic transactions for financial operations.
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from app.infrastructure.repositories.tenant_mixin import TenantMixin
from sqlalchemy import func, text

from app.domain.financial.payment import Payment, PaymentStatus, PaymentMethod
from app.domain.financial.receivable import Receivable, ReceivableStatus
from app.domain.financial.expense import Expense, ExpenseStatus, ExpenseCategory
from app.domain.financial.cash_movement import CashMovement, CashMovementType
from app.domain.financial.ledger import FinancialLedgerEntry, LedgerEventType
from app.domain.financial.repository import (
    PaymentRepository,
    ReceivableRepository,
    ExpenseRepository,
    CashMovementRepository,
    FinancialLedgerRepository,
)
from app.infrastructure.repositories.financial_models import (
    PaymentModel,
    ReceivableModel,
    ExpenseModel,
    CashMovementModel,
    FinancialLedgerModel,
)


def _to_decimal(val) -> Decimal:
    if val is None:
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class SQLAlchemyPaymentRepository(TenantMixin, PaymentRepository):
    def __init__(self, db: Session, tenant_id: str = "default"):
        super().__init__(db, tenant_id)

    def _to_entity(self, m: PaymentModel) -> Payment:
        return Payment(
            id=m.id,
            order_codigo=m.order_codigo,
            amount=_to_decimal(m.amount),
            method=PaymentMethod(m.method),
            status=PaymentStatus(m.status),
            paid_at=m.paid_at,
            reference=m.reference,
            idempotency_key=m.idempotency_key,
            notes=m.notes,
            created_at=m.created_at,
        )

    def create(self, payment: Payment) -> Payment:
        model = PaymentModel(
            tenant_id=self.tenant_id,
            order_codigo=payment.order_codigo,
            amount=payment.amount,
            method=payment.method.value,
            status=payment.status.value,
            paid_at=payment.paid_at,
            reference=payment.reference,
            idempotency_key=payment.idempotency_key,
            notes=payment.notes,
            created_at=payment.created_at,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def update_status(self, payment_id: int, status, notes: Optional[str] = None) -> Payment:
        model = self._filter_by_tenant(PaymentModel).filter(PaymentModel.id == payment_id).first()
        if not model:
            raise ValueError(f"Payment {payment_id} not found")
        model.status = status.value if hasattr(status, "value") else status
        if notes is not None:
            model.notes = notes
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def get_by_id(self, payment_id: int) -> Optional[Payment]:
        model = self._filter_by_tenant(PaymentModel).filter(PaymentModel.id == payment_id).first()
        return self._to_entity(model) if model else None

    def get_by_order(self, order_codigo: str) -> List[Payment]:
        models = (
            self._filter_by_tenant(PaymentModel)
            .filter(PaymentModel.order_codigo == order_codigo)
            .order_by(PaymentModel.created_at)
            .all()
        )
        return [self._to_entity(m) for m in models]

    def get_by_idempotency_key(self, key: str) -> Optional[Payment]:
        model = self._filter_by_tenant(PaymentModel).filter(PaymentModel.idempotency_key == key).first()
        return self._to_entity(model) if model else None

    def list_all(
        self, status: Optional[PaymentStatus] = None, page: int = 1, page_size: int = 50
    ) -> Tuple[List[Payment], int]:
        q = self._filter_by_tenant(PaymentModel)
        if status:
            q = q.filter(PaymentModel.status == status.value)
        total = q.count()
        offset = (page - 1) * page_size
        models = q.order_by(PaymentModel.created_at.desc()).offset(offset).limit(page_size).all()
        return [self._to_entity(m) for m in models], total

    def total_paid_for_order(self, order_codigo: str) -> Decimal:
        result = (
            self.db.query(func.coalesce(func.sum(PaymentModel.amount), 0))
            .filter(
                PaymentModel.tenant_id == self.tenant_id,
                PaymentModel.order_codigo == order_codigo,
                PaymentModel.status.in_(["PAID", "PARTIAL"]),
            )
            .scalar()
        )
        return _to_decimal(result)

    def exists_by_idempotency_key(self, key: str) -> bool:
        return self._filter_by_tenant(PaymentModel).filter(PaymentModel.idempotency_key == key).count() > 0


class SQLAlchemyReceivableRepository(TenantMixin, ReceivableRepository):
    def __init__(self, db: Session, tenant_id: str = "default"):
        super().__init__(db, tenant_id)

    def _to_entity(self, m: ReceivableModel) -> Receivable:
        return Receivable(
            id=m.id,
            customer_codigo=m.customer_codigo,
            order_codigo=m.order_codigo,
            original_amount=_to_decimal(m.original_amount),
            paid_amount=_to_decimal(m.paid_amount),
            due_date=m.due_date,
            status=ReceivableStatus(m.status),
            created_at=m.created_at,
            settled_at=m.settled_at,
        )

    def _from_entity(self, r: Receivable) -> ReceivableModel:
        return ReceivableModel(
            tenant_id=self.tenant_id,
            id=r.id,
            customer_codigo=r.customer_codigo,
            order_codigo=r.order_codigo,
            original_amount=r.original_amount,
            paid_amount=r.paid_amount,
            due_date=r.due_date,
            status=r.status.value,
            created_at=r.created_at,
            settled_at=r.settled_at,
        )

    def create(self, receivable: Receivable) -> Receivable:
        model = self._from_entity(receivable)
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def update(self, receivable: Receivable) -> Receivable:
        model = self._filter_by_tenant(ReceivableModel).filter(ReceivableModel.id == receivable.id).first()
        if not model:
            raise ValueError(f"Receivable {receivable.id} not found")
        model.paid_amount = receivable.paid_amount
        model.status = receivable.status.value
        model.settled_at = receivable.settled_at
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def get_by_id(self, receivable_id: int) -> Optional[Receivable]:
        model = self._filter_by_tenant(ReceivableModel).filter(ReceivableModel.id == receivable_id).first()
        return self._to_entity(model) if model else None

    def get_by_order(self, order_codigo: str) -> Optional[Receivable]:
        model = self._filter_by_tenant(ReceivableModel).filter(ReceivableModel.order_codigo == order_codigo).first()
        return self._to_entity(model) if model else None

    def get_by_customer(self, customer_codigo: str) -> List[Receivable]:
        models = (
            self._filter_by_tenant(ReceivableModel)
            .filter(ReceivableModel.customer_codigo == customer_codigo)
            .order_by(ReceivableModel.created_at.desc())
            .all()
        )
        return [self._to_entity(m) for m in models]

    def list_open(self, page: int = 1, page_size: int = 50) -> Tuple[List[Receivable], int]:
        q = self._filter_by_tenant(ReceivableModel).filter(ReceivableModel.status.in_(["OPEN", "PARTIAL", "OVERDUE"]))
        total = q.count()
        offset = (page - 1) * page_size
        models = q.order_by(ReceivableModel.due_date.asc()).offset(offset).limit(page_size).all()
        return [self._to_entity(m) for m in models], total

    def list_overdue(self, page: int = 1, page_size: int = 50) -> Tuple[List[Receivable], int]:
        q = self._filter_by_tenant(ReceivableModel).filter(ReceivableModel.status == "OVERDUE")
        total = q.count()
        offset = (page - 1) * page_size
        models = q.order_by(ReceivableModel.due_date.asc()).offset(offset).limit(page_size).all()
        return [self._to_entity(m) for m in models], total

    def total_outstanding_for_customer(self, customer_codigo: str) -> Decimal:
        result = (
            self.db.query(func.coalesce(func.sum(ReceivableModel.original_amount - ReceivableModel.paid_amount), 0))
            .filter(
                ReceivableModel.tenant_id == self.tenant_id,
                ReceivableModel.customer_codigo == customer_codigo,
                ReceivableModel.status.in_(["OPEN", "PARTIAL", "OVERDUE"]),
            )
            .scalar()
        )
        return _to_decimal(result)

    def update_overdue_status(self, current_date: datetime) -> int:
        result = self.db.execute(
            text(
                "UPDATE receivables SET status = 'OVERDUE' "
                "WHERE status IN ('OPEN', 'PARTIAL') "
                "AND due_date < :now "
                "AND (original_amount - paid_amount) > 0"
            ),
            {"now": current_date, "tenant_id": self.tenant_id},
        )
        self.db.commit()
        return result.rowcount


class SQLAlchemyExpenseRepository(TenantMixin, ExpenseRepository):
    def __init__(self, db: Session, tenant_id: str = "default"):
        super().__init__(db, tenant_id)

    def _to_entity(self, m: ExpenseModel) -> Expense:
        return Expense(
            id=m.id,
            description=m.description,
            amount=_to_decimal(m.amount),
            category=ExpenseCategory(m.category),
            date=m.date,
            payment_method=m.payment_method,
            notes=m.notes,
            status=ExpenseStatus(m.status),
            created_at=m.created_at,
        )

    def create(self, expense: Expense) -> Expense:
        model = ExpenseModel(
            tenant_id=self.tenant_id,
            description=expense.description,
            amount=expense.amount,
            category=expense.category.value,
            date=expense.date,
            payment_method=expense.payment_method,
            notes=expense.notes,
            status=expense.status.value,
            created_at=expense.created_at,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def get_by_id(self, expense_id: int) -> Optional[Expense]:
        model = self._filter_by_tenant(ExpenseModel).filter(ExpenseModel.id == expense_id).first()
        return self._to_entity(model) if model else None

    def list_all(
        self, status: Optional[ExpenseStatus] = None, page: int = 1, page_size: int = 50
    ) -> Tuple[List[Expense], int]:
        q = self._filter_by_tenant(ExpenseModel)
        if status:
            q = q.filter(ExpenseModel.status == status.value)
        total = q.count()
        offset = (page - 1) * page_size
        models = q.order_by(ExpenseModel.date.desc()).offset(offset).limit(page_size).all()
        return [self._to_entity(m) for m in models], total

    def cancel(self, expense_id: int) -> Optional[Expense]:
        model = self._filter_by_tenant(ExpenseModel).filter(ExpenseModel.id == expense_id).first()
        if not model:
            return None
        model.status = "CANCELLED"
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def total_by_period(self, start: datetime, end: datetime) -> Decimal:
        result = (
            self.db.query(func.coalesce(func.sum(ExpenseModel.amount), 0))
            .filter(
                ExpenseModel.tenant_id == self.tenant_id,
                ExpenseModel.date >= start,
                ExpenseModel.date < end,
                ExpenseModel.status == "ACTIVE",
            )
            .scalar()
        )
        return _to_decimal(result)


class SQLAlchemyCashMovementRepository(TenantMixin, CashMovementRepository):
    def __init__(self, db: Session, tenant_id: str = "default"):
        super().__init__(db, tenant_id)

    def _to_entity(self, m: CashMovementModel) -> CashMovement:
        return CashMovement(
            id=m.id,
            type=CashMovementType(m.type),
            amount=_to_decimal(m.amount),
            description=m.description,
            reference_type=m.reference_type,
            reference_id=m.reference_id,
            balance_after=_to_decimal(m.balance_after),
            created_at=m.created_at,
        )

    def create(self, movement: CashMovement) -> CashMovement:
        model = CashMovementModel(
            tenant_id=self.tenant_id,
            type=movement.type.value,
            amount=movement.amount,
            description=movement.description,
            reference_type=movement.reference_type,
            reference_id=movement.reference_id,
            balance_after=movement.balance_after,
            created_at=movement.created_at,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def get_by_id(self, movement_id: int) -> Optional[CashMovement]:
        model = self._filter_by_tenant(CashMovementModel).filter(CashMovementModel.id == movement_id).first()
        return self._to_entity(model) if model else None

    def list_all(
        self, type_filter: Optional[CashMovementType] = None, page: int = 1, page_size: int = 50
    ) -> Tuple[List[CashMovement], int]:
        q = self._filter_by_tenant(CashMovementModel)
        if type_filter:
            q = q.filter(CashMovementModel.type == type_filter.value)
        total = q.count()
        offset = (page - 1) * page_size
        models = q.order_by(CashMovementModel.created_at.desc()).offset(offset).limit(page_size).all()
        return [self._to_entity(m) for m in models], total

    def current_balance(self) -> Decimal:
        last = self._filter_by_tenant(CashMovementModel).order_by(CashMovementModel.id.desc()).first()
        if last:
            return _to_decimal(last.balance_after)
        return Decimal("0.00")

    def total_by_type_and_period(self, movement_type: CashMovementType, start: datetime, end: datetime) -> Decimal:
        result = (
            self.db.query(func.coalesce(func.sum(CashMovementModel.amount), 0))
            .filter(
                CashMovementModel.tenant_id == self.tenant_id,
                CashMovementModel.type == movement_type.value,
                CashMovementModel.created_at >= start,
                CashMovementModel.created_at < end,
            )
            .scalar()
        )
        return _to_decimal(result)


class SQLAlchemyFinancialLedgerRepository(TenantMixin, FinancialLedgerRepository):
    def __init__(self, db: Session, tenant_id: str = "default"):
        super().__init__(db, tenant_id)

    def _to_entity(self, m: FinancialLedgerModel) -> FinancialLedgerEntry:
        return FinancialLedgerEntry(
            id=m.id,
            event_type=LedgerEventType(m.event_type),
            amount=_to_decimal(m.amount),
            reference_type=m.reference_type,
            reference_id=m.reference_id,
            description=m.description,
            created_at=m.created_at,
        )

    def create(self, entry: FinancialLedgerEntry) -> FinancialLedgerEntry:
        model = FinancialLedgerModel(
            tenant_id=self.tenant_id,
            event_type=entry.event_type.value,
            amount=entry.amount,
            reference_type=entry.reference_type,
            reference_id=entry.reference_id,
            description=entry.description,
            created_at=entry.created_at,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def list_all(
        self, event_type: Optional[LedgerEventType] = None, page: int = 1, page_size: int = 50
    ) -> Tuple[List[FinancialLedgerEntry], int]:
        q = self._filter_by_tenant(FinancialLedgerModel)
        if event_type:
            q = q.filter(FinancialLedgerModel.event_type == event_type.value)
        total = q.count()
        offset = (page - 1) * page_size
        models = q.order_by(FinancialLedgerModel.created_at.desc()).offset(offset).limit(page_size).all()
        return [self._to_entity(m) for m in models], total

    def exists(self, reference_type: str, reference_id: str, event_type: LedgerEventType) -> bool:
        return (
            self._filter_by_tenant(FinancialLedgerModel)
            .filter(
                FinancialLedgerModel.reference_type == reference_type,
                FinancialLedgerModel.reference_id == reference_id,
                FinancialLedgerModel.event_type == event_type.value,
            )
            .count()
            > 0
        )
