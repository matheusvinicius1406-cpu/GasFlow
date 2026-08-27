"""
Financial API Endpoints — FASE 8

REST API for payments, receivables, expenses, cash movements.
All derived values calculated by backend.
"""

from datetime import datetime
from decimal import Decimal
from math import ceil
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.infrastructure.database.connection import SessionLocal
from app.infrastructure.repositories.financial_repositories import (
    SQLAlchemyPaymentRepository, SQLAlchemyReceivableRepository,
    SQLAlchemyExpenseRepository, SQLAlchemyCashMovementRepository,
    SQLAlchemyFinancialLedgerRepository,
)
from app.application.financial.use_cases import (
    RegisterPaymentUseCase, RegisterExpenseUseCase,
    RefundPaymentUseCase, FinancialReportsUseCase,
)
from app.presentation.schemas.financial import (
    PaymentCreate, PaymentResponse, PaymentListResponse,
    ReceivableResponse, ReceivableListResponse,
    ExpenseCreate, ExpenseResponse, ExpenseListResponse,
    CashMovementResponse, CashMovementListResponse,
    DailySummaryResponse,
)

router = APIRouter(prefix="/finance", tags=["finance"])


# ── Payments ─────────────────────────────────────────

@router.get("/payments", response_model=PaymentListResponse)
def list_payments(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    db = SessionLocal()
    try:
        repo = SQLAlchemyPaymentRepository(db)
        from app.domain.financial.payment import PaymentStatus
        s = PaymentStatus(status) if status else None
        items, total = repo.list_all(status=s, page=page, page_size=page_size)
        return PaymentListResponse(
            items=[PaymentResponse.model_validate(_to_dict(i)) for i in items],
            total=total, page=page, page_size=page_size,
            total_pages=ceil(total / page_size) if page_size else 1,
        )
    finally:
        db.close()


@router.post("/orders/{order_codigo}/payments", response_model=dict)
def register_payment(order_codigo: str, data: PaymentCreate):
    db = SessionLocal()
    try:
        uc = RegisterPaymentUseCase(
            payment_repo=SQLAlchemyPaymentRepository(db),
            receivable_repo=SQLAlchemyReceivableRepository(db),
            cash_repo=SQLAlchemyCashMovementRepository(db),
            ledger_repo=SQLAlchemyFinancialLedgerRepository(db),
        )
        result = uc.execute({
            "order_codigo": order_codigo,
            "amount": data.amount,
            "method": data.method,
            "reference": data.reference,
            "idempotency_key": data.idempotency_key,
            "notes": data.notes,
        })
        return {
            "status": result["status"],
            "payment": PaymentResponse.model_validate(_to_dict(result["payment"])),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()


@router.post("/payments/{payment_id}/refund", response_model=dict)
def refund_payment(payment_id: int, reason: str = ""):
    db = SessionLocal()
    try:
        uc = RefundPaymentUseCase(
            payment_repo=SQLAlchemyPaymentRepository(db),
            receivable_repo=SQLAlchemyReceivableRepository(db),
            cash_repo=SQLAlchemyCashMovementRepository(db),
            ledger_repo=SQLAlchemyFinancialLedgerRepository(db),
        )
        result = uc.execute(payment_id, reason)
        return {"status": result["status"], "message": "Refund processed"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()


# ── Receivables ──────────────────────────────────────

@router.get("/receivables", response_model=ReceivableListResponse)
def list_receivables(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    db = SessionLocal()
    try:
        repo = SQLAlchemyReceivableRepository(db)
        if status and status == "OVERDUE":
            items, total = repo.list_overdue(page=page, page_size=page_size)
        elif status and status in ("OPEN", "PARTIAL"):
            items, total = repo.list_open(page=page, page_size=page_size)
        else:
            items, total = repo.list_open(page=page, page_size=page_size)
        return ReceivableListResponse(
            items=[_receivable_to_response(i) for i in items],
            total=total, page=page, page_size=page_size,
            total_pages=ceil(total / page_size) if page_size else 1,
        )
    finally:
        db.close()


# ── Expenses ─────────────────────────────────────────

@router.get("/expenses", response_model=ExpenseListResponse)
def list_expenses(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    db = SessionLocal()
    try:
        repo = SQLAlchemyExpenseRepository(db)
        from app.domain.financial.expense import ExpenseStatus
        s = ExpenseStatus(status) if status else None
        items, total = repo.list_all(status=s, page=page, page_size=page_size)
        return ExpenseListResponse(
            items=[ExpenseResponse.model_validate(_to_dict(i)) for i in items],
            total=total, page=page, page_size=page_size,
            total_pages=ceil(total / page_size) if page_size else 1,
        )
    finally:
        db.close()


@router.post("/expenses", response_model=dict)
def register_expense(data: ExpenseCreate):
    db = SessionLocal()
    try:
        uc = RegisterExpenseUseCase(
            expense_repo=SQLAlchemyExpenseRepository(db),
            cash_repo=SQLAlchemyCashMovementRepository(db),
            ledger_repo=SQLAlchemyFinancialLedgerRepository(db),
        )
        result = uc.execute({
            "description": data.description,
            "amount": data.amount,
            "category": data.category,
            "date": data.date,
            "payment_method": data.payment_method,
            "notes": data.notes,
        })
        return {"status": "created", "expense": ExpenseResponse.model_validate(_to_dict(result["expense"]))}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()


@router.post("/expenses/{expense_id}/cancel", response_model=dict)
def cancel_expense(expense_id: int):
    db = SessionLocal()
    try:
        repo = SQLAlchemyExpenseRepository(db)
        expense = repo.cancel(expense_id)
        if not expense:
            raise HTTPException(status_code=404, detail="Expense not found")
        return {"status": "cancelled", "expense": ExpenseResponse.model_validate(_to_dict(expense))}
    finally:
        db.close()


# ── Cash Movements ───────────────────────────────────

@router.get("/cash", response_model=CashMovementListResponse)
def list_cash_movements(
    type_filter: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    db = SessionLocal()
    try:
        repo = SQLAlchemyCashMovementRepository(db)
        from app.domain.financial.cash_movement import CashMovementType
        t = CashMovementType(type_filter) if type_filter else None
        items, total = repo.list_all(type_filter=t, page=page, page_size=page_size)
        return CashMovementListResponse(
            items=[CashMovementResponse.model_validate(_to_dict(i)) for i in items],
            total=total, page=page, page_size=page_size,
            total_pages=ceil(total / page_size) if page_size else 1,
        )
    finally:
        db.close()


@router.get("/cash/balance", response_model=dict)
def get_cash_balance():
    db = SessionLocal()
    try:
        repo = SQLAlchemyCashMovementRepository(db)
        balance = repo.current_balance()
        return {"balance": balance}
    finally:
        db.close()


# ── Reports ──────────────────────────────────────────

@router.get("/reports/daily", response_model=DailySummaryResponse)
def daily_report(date: Optional[str] = Query(None)):
    db = SessionLocal()
    try:
        target_date = datetime.fromisoformat(date) if date else datetime.utcnow()
        uc = FinancialReportsUseCase(
            payment_repo=SQLAlchemyPaymentRepository(db),
            receivable_repo=SQLAlchemyReceivableRepository(db),
            expense_repo=SQLAlchemyExpenseRepository(db),
            cash_repo=SQLAlchemyCashMovementRepository(db),
        )
        result = uc.daily_summary(target_date)
        return DailySummaryResponse(**result)
    finally:
        db.close()


# ── Helpers ──────────────────────────────────────────

def _to_dict(entity) -> dict:
    """Convert domain entity to dict for Pydantic."""
    d = {}
    for k, v in entity.__dict__.items():
        if k.startswith("_"):
            continue
        d[k] = v
    return d


def _receivable_to_response(r) -> ReceivableResponse:
    return ReceivableResponse(
        id=r.id,
        customer_codigo=r.customer_codigo,
        order_codigo=r.order_codigo,
        original_amount=r.original_amount,
        paid_amount=r.paid_amount,
        remaining_amount=r.remaining_amount,
        due_date=r.due_date,
        status=r.status.value if hasattr(r.status, 'value') else r.status,
        created_at=r.created_at,
        settled_at=r.settled_at,
    )
