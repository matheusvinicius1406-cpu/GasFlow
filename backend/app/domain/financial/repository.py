"""
Financial Repository Interfaces — FASE 8

Abstract interfaces for financial data access.
All monetary values use Decimal.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Tuple

from app.domain.financial.payment import Payment, PaymentStatus
from app.domain.financial.receivable import Receivable
from app.domain.financial.expense import Expense, ExpenseStatus
from app.domain.financial.cash_movement import CashMovement, CashMovementType
from app.domain.financial.ledger import FinancialLedgerEntry, LedgerEventType


class PaymentRepository(ABC):
    @abstractmethod
    def create(self, payment: Payment) -> Payment:
        ...

    @abstractmethod
    def update_status(self, payment_id: int, status, notes: Optional[str] = None) -> Payment:
        ...

    @abstractmethod
    def get_by_id(self, payment_id: int) -> Optional[Payment]:
        ...

    @abstractmethod
    def get_by_order(self, order_codigo: str) -> List[Payment]:
        ...

    @abstractmethod
    def get_by_idempotency_key(self, key: str) -> Optional[Payment]:
        ...

    @abstractmethod
    def list_all(self, status: Optional[PaymentStatus] = None,
                 page: int = 1, page_size: int = 50) -> Tuple[List[Payment], int]:
        ...

    @abstractmethod
    def total_paid_for_order(self, order_codigo: str) -> Decimal:
        ...

    @abstractmethod
    def exists_by_idempotency_key(self, key: str) -> bool:
        ...


class ReceivableRepository(ABC):
    @abstractmethod
    def create(self, receivable: Receivable) -> Receivable:
        ...

    @abstractmethod
    def update(self, receivable: Receivable) -> Receivable:
        ...

    @abstractmethod
    def get_by_id(self, receivable_id: int) -> Optional[Receivable]:
        ...

    @abstractmethod
    def get_by_order(self, order_codigo: str) -> Optional[Receivable]:
        ...

    @abstractmethod
    def get_by_customer(self, customer_codigo: str) -> List[Receivable]:
        ...

    @abstractmethod
    def list_open(self, page: int = 1, page_size: int = 50) -> Tuple[List[Receivable], int]:
        ...

    @abstractmethod
    def list_overdue(self, page: int = 1, page_size: int = 50) -> Tuple[List[Receivable], int]:
        ...

    @abstractmethod
    def total_outstanding_for_customer(self, customer_codigo: str) -> Decimal:
        ...

    @abstractmethod
    def update_overdue_status(self, current_date: datetime) -> int:
        ...


class ExpenseRepository(ABC):
    @abstractmethod
    def create(self, expense: Expense) -> Expense:
        ...

    @abstractmethod
    def get_by_id(self, expense_id: int) -> Optional[Expense]:
        ...

    @abstractmethod
    def list_all(self, status: Optional[ExpenseStatus] = None,
                 page: int = 1, page_size: int = 50) -> Tuple[List[Expense], int]:
        ...

    @abstractmethod
    def cancel(self, expense_id: int) -> Optional[Expense]:
        ...

    @abstractmethod
    def total_by_period(self, start: datetime, end: datetime) -> Decimal:
        ...


class CashMovementRepository(ABC):
    @abstractmethod
    def create(self, movement: CashMovement) -> CashMovement:
        ...

    @abstractmethod
    def get_by_id(self, movement_id: int) -> Optional[CashMovement]:
        ...

    @abstractmethod
    def list_all(self, type_filter: Optional[CashMovementType] = None,
                 page: int = 1, page_size: int = 50) -> Tuple[List[CashMovement], int]:
        ...

    @abstractmethod
    def current_balance(self) -> Decimal:
        ...

    @abstractmethod
    def total_by_type_and_period(self, movement_type: CashMovementType,
                                  start: datetime, end: datetime) -> Decimal:
        ...


class FinancialLedgerRepository(ABC):
    @abstractmethod
    def create(self, entry: FinancialLedgerEntry) -> FinancialLedgerEntry:
        ...

    @abstractmethod
    def list_all(self, event_type: Optional[LedgerEventType] = None,
                 page: int = 1, page_size: int = 50) -> Tuple[List[FinancialLedgerEntry], int]:
        ...

    @abstractmethod
    def exists(self, reference_type: str, reference_id: str,
               event_type: LedgerEventType) -> bool:
        ...
