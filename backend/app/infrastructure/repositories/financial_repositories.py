"""
Financial Repository Implementations — FASE 8

All monetary values stored/returned as Decimal.
Atomic transactions for financial operations.
"""

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Tuple, Dict
from sqlalchemy.orm import Session
from app.infrastructure.repositories.tenant_mixin import TenantMixin
from sqlalchemy import func, text, or_

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


def _parse_day(value) -> date:
    """Normaliza a chave devolvida por `func.date(...)`.

    SQLite devolve string 'YYYY-MM-DD'; PostgreSQL devolve `date`. Aceita os
    dois (e `datetime`, por segurança) para os agrupamentos por dia serem
    portáveis entre os bancos suportados.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _to_decimal(val) -> Decimal:
    if val is None:
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _apply_common_filters(
    q,
    model,
    *,
    q_text: Optional[str] = None,
    search_fields: Tuple[str, ...] = (),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    date_column=None,
):
    """Filtros aditivos compartilhados pelas listagens financeiras.

    - `q_text`: LIKE em `search_fields` (colunas do model).
    - `date_from`/`date_to`: faixa em `date_column`; `date_to` é INCLUSIVO
      no dia (YYYY-MM-DD vira < dia seguinte 00:00), mesmo ritual do
      `/finance/reports/period`.
    """
    if q_text:
        pattern = f"%{q_text}%"
        clauses = [getattr(model, name).ilike(pattern) for name in search_fields]
        q = q.filter(or_(*clauses))
    if date_from is not None:
        q = q.filter(date_column >= date_from)
    if date_to is not None:
        q = q.filter(date_column < date_to)
    return q


def _apply_order(
    q,
    model,
    *,
    order_by: Optional[str],
    order: Optional[str],
    allowed: Dict[str, str],
    default_col: str,
    default_dir: str,
):
    """Ordenação por whitelist. `order_by` inválido levanta ValueError (→ 400)."""
    col_name = order_by or default_col
    if col_name not in allowed:
        raise ValueError(f"order_by inválido: use um de {sorted(allowed)}")
    direction = (order or default_dir).lower()
    if direction not in ("asc", "desc"):
        raise ValueError("order inválido: use 'asc' ou 'desc'")
    column = getattr(model, allowed[col_name])
    return q.order_by(column.asc() if direction == "asc" else column.desc())


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
        self,
        status: Optional[PaymentStatus] = None,
        page: int = 1,
        page_size: int = 50,
        *,
        q: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        order_by: Optional[str] = None,
        order: Optional[str] = None,
    ) -> Tuple[List[Payment], int]:
        query = self._filter_by_tenant(PaymentModel)
        if status:
            query = query.filter(PaymentModel.status == status.value)
        # Data do lançamento: paid_at quando existe, senão o registro.
        query = _apply_common_filters(
            query,
            PaymentModel,
            q_text=q,
            search_fields=("order_codigo", "reference", "notes"),
            date_from=date_from,
            date_to=date_to,
            date_column=func.coalesce(PaymentModel.paid_at, PaymentModel.created_at),
        )
        total = query.count()
        offset = (page - 1) * page_size
        query = _apply_order(
            query,
            PaymentModel,
            order_by=order_by,
            order=order,
            allowed={
                "created_at": "created_at",
                "paid_at": "paid_at",
                "amount": "amount",
                "order_codigo": "order_codigo",
                "status": "status",
                "method": "method",
            },
            default_col="created_at",
            default_dir="desc",
        )
        models = query.offset(offset).limit(page_size).all()
        return [self._to_entity(m) for m in models], total

    def totals_by_method(self, start: datetime, end: datetime) -> Dict[str, Decimal]:
        """Pagamentos recebidos (PAID/PARTIAL) por forma no período [start, end).

        REFUNDED fica de fora: dinheiro devolvido não conta como recebido.
        """
        rows = (
            self.db.query(PaymentModel.method, func.coalesce(func.sum(PaymentModel.amount), 0))
            .filter(
                PaymentModel.tenant_id == self.tenant_id,
                PaymentModel.status.in_(["PAID", "PARTIAL"]),
                PaymentModel.paid_at >= start,
                PaymentModel.paid_at < end,
            )
            .group_by(PaymentModel.method)
            .all()
        )
        return {method: _to_decimal(total) for method, total in rows}

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

    def _list_receivables(
        self,
        base,
        page: int,
        page_size: int,
        *,
        q: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        order_by: Optional[str] = None,
        order: Optional[str] = None,
    ) -> Tuple[List[Receivable], int]:
        base = _apply_common_filters(
            base,
            ReceivableModel,
            q_text=q,
            search_fields=("customer_codigo", "order_codigo"),
            date_from=date_from,
            date_to=date_to,
            date_column=ReceivableModel.due_date,
        )
        total = base.count()
        offset = (page - 1) * page_size
        base = _apply_order(
            base,
            ReceivableModel,
            order_by=order_by,
            order=order,
            allowed={
                "due_date": "due_date",
                "created_at": "created_at",
                "original_amount": "original_amount",
                "paid_amount": "paid_amount",
                "status": "status",
                "customer_codigo": "customer_codigo",
            },
            default_col="due_date",
            default_dir="asc",
        )
        models = base.offset(offset).limit(page_size).all()
        return [self._to_entity(m) for m in models], total

    def list_open(
        self,
        page: int = 1,
        page_size: int = 50,
        *,
        q: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        order_by: Optional[str] = None,
        order: Optional[str] = None,
    ) -> Tuple[List[Receivable], int]:
        base = self._filter_by_tenant(ReceivableModel).filter(
            ReceivableModel.status.in_(["OPEN", "PARTIAL", "OVERDUE"])
        )
        return self._list_receivables(
            base, page, page_size, q=q, date_from=date_from, date_to=date_to, order_by=order_by, order=order
        )

    def list_overdue(
        self,
        page: int = 1,
        page_size: int = 50,
        *,
        q: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        order_by: Optional[str] = None,
        order: Optional[str] = None,
    ) -> Tuple[List[Receivable], int]:
        base = self._filter_by_tenant(ReceivableModel).filter(ReceivableModel.status == "OVERDUE")
        return self._list_receivables(
            base, page, page_size, q=q, date_from=date_from, date_to=date_to, order_by=order_by, order=order
        )

    def list_open_all(self) -> List[Receivable]:
        """Todos os recebíveis em aberto — base do aging (poucas dezenas em uso real)."""
        models = (
            self._filter_by_tenant(ReceivableModel)
            .filter(ReceivableModel.status.in_(["OPEN", "PARTIAL", "OVERDUE"]))
            .order_by(ReceivableModel.due_date.asc())
            .all()
        )
        return [self._to_entity(m) for m in models]

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
        self,
        status: Optional[ExpenseStatus] = None,
        page: int = 1,
        page_size: int = 50,
        *,
        q: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        order_by: Optional[str] = None,
        order: Optional[str] = None,
    ) -> Tuple[List[Expense], int]:
        query = self._filter_by_tenant(ExpenseModel)
        if status:
            query = query.filter(ExpenseModel.status == status.value)
        query = _apply_common_filters(
            query,
            ExpenseModel,
            q_text=q,
            search_fields=("description", "notes"),
            date_from=date_from,
            date_to=date_to,
            date_column=ExpenseModel.date,
        )
        total = query.count()
        offset = (page - 1) * page_size
        query = _apply_order(
            query,
            ExpenseModel,
            order_by=order_by,
            order=order,
            allowed={
                "date": "date",
                "created_at": "created_at",
                "amount": "amount",
                "category": "category",
                "description": "description",
            },
            default_col="date",
            default_dir="desc",
        )
        models = query.offset(offset).limit(page_size).all()
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

    def totals_by_day(self, start: datetime, end: datetime) -> Dict[date, Decimal]:
        """Uma consulta agrupada por dia (em vez de N consultas) para o relatório."""
        day = func.date(ExpenseModel.date)
        rows = (
            self.db.query(day, func.coalesce(func.sum(ExpenseModel.amount), 0))
            .filter(
                ExpenseModel.tenant_id == self.tenant_id,
                ExpenseModel.date >= start,
                ExpenseModel.date < end,
                ExpenseModel.status == "ACTIVE",
            )
            .group_by(day)
            .all()
        )
        return {_parse_day(d): _to_decimal(total) for d, total in rows}

    def totals_by_category(self, start: datetime, end: datetime) -> Dict[str, Decimal]:
        """Despesas ATIVAS por categoria no período [start, end)."""
        rows = (
            self.db.query(ExpenseModel.category, func.coalesce(func.sum(ExpenseModel.amount), 0))
            .filter(
                ExpenseModel.tenant_id == self.tenant_id,
                ExpenseModel.date >= start,
                ExpenseModel.date < end,
                ExpenseModel.status == "ACTIVE",
            )
            .group_by(ExpenseModel.category)
            .all()
        )
        return {category: _to_decimal(total) for category, total in rows}


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
        self,
        type_filter: Optional[CashMovementType] = None,
        page: int = 1,
        page_size: int = 50,
        *,
        q: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        order_by: Optional[str] = None,
        order: Optional[str] = None,
    ) -> Tuple[List[CashMovement], int]:
        query = self._filter_by_tenant(CashMovementModel)
        if type_filter:
            query = query.filter(CashMovementModel.type == type_filter.value)
        query = _apply_common_filters(
            query,
            CashMovementModel,
            q_text=q,
            search_fields=("description", "reference_id"),
            date_from=date_from,
            date_to=date_to,
            date_column=CashMovementModel.created_at,
        )
        total = query.count()
        offset = (page - 1) * page_size
        query = _apply_order(
            query,
            CashMovementModel,
            order_by=order_by,
            order=order,
            allowed={
                "created_at": "created_at",
                "amount": "amount",
                "type": "type",
                "balance_after": "balance_after",
            },
            default_col="created_at",
            default_dir="desc",
        )
        models = query.offset(offset).limit(page_size).all()
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

    def receipts_by_day(self, start: datetime, end: datetime) -> Dict[date, Decimal]:
        """Uma consulta agrupada por dia (em vez de N consultas) para o relatório."""
        day = func.date(CashMovementModel.created_at)
        rows = (
            self.db.query(day, func.coalesce(func.sum(CashMovementModel.amount), 0))
            .filter(
                CashMovementModel.tenant_id == self.tenant_id,
                CashMovementModel.type == CashMovementType.RECEIPT.value,
                CashMovementModel.created_at >= start,
                CashMovementModel.created_at < end,
            )
            .group_by(day)
            .all()
        )
        return {_parse_day(d): _to_decimal(total) for d, total in rows}


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
