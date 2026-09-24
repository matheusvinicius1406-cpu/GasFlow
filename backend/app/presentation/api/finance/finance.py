"""
Financial API Endpoints — FASE 8

REST API for payments, receivables, expenses, cash movements.
All derived values calculated by backend.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from math import ceil
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from app.infrastructure.database.dependencies import get_db
from app.presentation.dependencies import get_tenant_context, require_permission
from app.domain.security.models import TenantContext

from app.infrastructure.repositories.auth_model import AuthAuditModel
from app.infrastructure.repositories.financial_models import FinanceBudgetModel, FinanceSavedReportModel
from app.infrastructure.repositories.financial_repositories import (
    SQLAlchemyPaymentRepository,
    SQLAlchemyReceivableRepository,
    SQLAlchemyExpenseRepository,
    SQLAlchemyCashMovementRepository,
    SQLAlchemyFinancialLedgerRepository,
    SQLAlchemyFinanceBudgetRepository,
    SQLAlchemySavedReportRepository,
)
from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository
from app.application.financial.audit import log_finance_audit
from app.application.financial.use_cases import (
    RegisterPaymentUseCase,
    RegisterExpenseUseCase,
    RefundPaymentUseCase,
    FinancialReportsUseCase,
)
from app.presentation.schemas.financial import (
    PaymentCreate,
    PaymentResponse,
    PaymentListResponse,
    ReceivableResponse,
    ReceivableListResponse,
    ExpenseCreate,
    ExpenseResponse,
    ExpenseListResponse,
    CashMovementResponse,
    CashMovementListResponse,
    DailySummaryResponse,
    PeriodSummaryResponse,
    CategoryBreakdownResponse,
    MethodBreakdownResponse,
    ReceivablesSummaryResponse,
    DreResponse,
    ProductsResponse,
    ProjectionResponse,
    TeamResponse,
    HourlyResponse,
    ConciliationResponse,
    BudgetItem,
    BudgetResponse,
    BudgetUpsertRequest,
    SavedReportCreate,
    SavedReportListResponse,
    SavedReportResponse,
    FinanceAuditItem,
    FinanceAuditResponse,
)

router = APIRouter(prefix="/finance", tags=["finance"])


# ── Helpers de período/filtros ───────────────────────


def _resolve_period(
    days: int,
    date_from: Optional[str],
    date_to: Optional[str],
) -> tuple[datetime, datetime]:
    """Resolve o período [start, end) dos relatórios financeiros.

    Sem `from`/`to`, usa os últimos `days` dias INCLUINDO hoje (30 → de 29
    dias atrás até hoje), que é a leitura que o operador espera do filtro.
    """
    if date_from or date_to:
        if not (date_from and date_to):
            raise HTTPException(400, "Informe 'from' e 'to' juntos (YYYY-MM-DD)")
        try:
            start = datetime.strptime(date_from, "%Y-%m-%d")
            end_day = datetime.strptime(date_to, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(400, "Data inválida: use YYYY-MM-DD") from exc
        if end_day < start:
            raise HTTPException(400, "'to' não pode ser anterior a 'from'")
        end = end_day + timedelta(days=1)
        if (end - start).days > 366:
            raise HTTPException(400, "Período máximo: 366 dias")
        return start, end

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    end = today + timedelta(days=1)
    return end - timedelta(days=days), end


def _parse_date_bounds(
    date_from: Optional[str],
    date_to: Optional[str],
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Faixa opcional das listagens: YYYY-MM-DD, `to` inclusivo no dia."""
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    if date_from:
        try:
            start = datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(400, "date_from inválida: use YYYY-MM-DD") from exc
    if date_to:
        try:
            end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
        except ValueError as exc:
            raise HTTPException(400, "date_to inválida: use YYYY-MM-DD") from exc
    if start and end and end <= start:
        raise HTTPException(400, "date_to não pode ser anterior a date_from")
    return start, end


def _order_or_400(fn, **kwargs):
    """Roda o repositório traduzindo ValueError de order_by/order em 400."""
    try:
        return fn(**kwargs)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _enum_or_400(enum_cls, value: Optional[str], label: str):
    """Converte query param em enum; valor desconhecido → 400 (não 500)."""
    if not value:
        return None
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise HTTPException(400, f"{label} inválido: {value!r}") from exc


# ── Payments ─────────────────────────────────────────


@router.get("/payments", response_model=PaymentListResponse)
def list_payments(
    status: Optional[str] = Query(None),
    order_codigo: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Busca em order_codigo, reference ou notes"),
    date_from: Optional[str] = Query(None, alias="date_from", description="Início YYYY-MM-DD (paid_at/created_at)"),
    date_to: Optional[str] = Query(None, alias="date_to", description="Fim YYYY-MM-DD inclusivo"),
    order_by: Optional[str] = Query(None, description="created_at | paid_at | amount | order_codigo | status | method"),
    order: Optional[str] = Query(None, description="asc | desc (padrão: desc por created_at)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    repo = SQLAlchemyPaymentRepository(db, ctx.tenant_id)

    # Filter by specific order
    if order_codigo:
        items = repo.get_by_order(order_codigo)
        return PaymentListResponse(
            items=[PaymentResponse.model_validate(_to_dict(i)) for i in items],
            total=len(items),
            page=1,
            page_size=len(items) or 1,
            total_pages=1,
        )

    from app.domain.financial.payment import PaymentStatus

    s = _enum_or_400(PaymentStatus, status, "status")
    date_start, date_end = _parse_date_bounds(date_from, date_to)
    items, total = _order_or_400(
        repo.list_all,
        status=s,
        page=page,
        page_size=page_size,
        q=q,
        date_from=date_start,
        date_to=date_end,
        order_by=order_by,
        order=order,
    )
    return PaymentListResponse(
        items=[PaymentResponse.model_validate(_to_dict(i)) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if page_size else 1,
    )


@router.post("/orders/{order_codigo}/payments", response_model=dict)
def register_payment(
    order_codigo: str,
    data: PaymentCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    uc = RegisterPaymentUseCase(
        payment_repo=SQLAlchemyPaymentRepository(db, ctx.tenant_id),
        receivable_repo=SQLAlchemyReceivableRepository(db, ctx.tenant_id),
        cash_repo=SQLAlchemyCashMovementRepository(db, ctx.tenant_id),
        ledger_repo=SQLAlchemyFinancialLedgerRepository(db, ctx.tenant_id),
        order_repo=SQLAlchemyOrderRepository(db, ctx.tenant_id),
    )
    try:
        result = uc.execute(
            {
                "order_codigo": order_codigo,
                "amount": data.amount,
                "method": data.method,
                "reference": data.reference,
                "idempotency_key": data.idempotency_key,
                "notes": data.notes,
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    payment = result["payment"]
    if result["status"] == "created":
        log_finance_audit(
            db,
            tenant_id=ctx.tenant_id,
            actor_id=ctx.user_id,
            action="payment.registered",
            resource="payment",
            resource_id=str(payment.id),
            after={
                "order_codigo": payment.order_codigo,
                "amount": payment.amount,
                "method": payment.method,
                "status": payment.status,
            },
        )
    return {
        "status": result["status"],
        "payment": PaymentResponse.model_validate(_to_dict(payment)),
    }


@router.post("/payments/{payment_id}/refund", response_model=dict)
def refund_payment(
    payment_id: int,
    reason: str = "",
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    uc = RefundPaymentUseCase(
        payment_repo=SQLAlchemyPaymentRepository(db, ctx.tenant_id),
        receivable_repo=SQLAlchemyReceivableRepository(db, ctx.tenant_id),
        cash_repo=SQLAlchemyCashMovementRepository(db, ctx.tenant_id),
        ledger_repo=SQLAlchemyFinancialLedgerRepository(db, ctx.tenant_id),
    )
    try:
        result = uc.execute(payment_id, reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    payment = result["payment"]
    # Use case devolve "status" só no atalho already_refunded; no caminho de
    # sucesso o status real é o do payment. (Antes result["status"] KeyError.)
    status = result.get("status") or "refunded"
    if status != "already_refunded":
        log_finance_audit(
            db,
            tenant_id=ctx.tenant_id,
            actor_id=ctx.user_id,
            action="payment.refunded",
            resource="payment",
            resource_id=str(payment.id),
            after={
                "order_codigo": payment.order_codigo,
                "amount": payment.amount,
                "status": payment.status,
                "reason": reason or "",
            },
        )
    return {"status": status, "message": "Refund processed"}


# ── Receivables ──────────────────────────────────────


@router.get("/receivables", response_model=ReceivableListResponse)
def list_receivables(
    status: Optional[str] = Query(None),
    order_codigo: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Busca em customer_codigo ou order_codigo"),
    date_from: Optional[str] = Query(None, description="Vencimento a partir de YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="Vencimento até YYYY-MM-DD (inclusivo)"),
    order_by: Optional[str] = Query(
        None, description="due_date | created_at | original_amount | paid_amount | status | customer_codigo"
    ),
    order: Optional[str] = Query(None, description="asc | desc (padrão: asc por due_date)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    repo = SQLAlchemyReceivableRepository(db, ctx.tenant_id)

    # Filter by specific order — returns single receivable
    if order_codigo:
        receivable = repo.get_by_order(order_codigo)
        items = [receivable] if receivable else []
        return ReceivableListResponse(
            items=[_receivable_to_response(i) for i in items],
            total=len(items),
            page=1,
            page_size=1,
            total_pages=1,
        )

    date_start, date_end = _parse_date_bounds(date_from, date_to)
    extras = dict(q=q, date_from=date_start, date_to=date_end, order_by=order_by, order=order)
    if status and status == "OVERDUE":
        items, total = _order_or_400(repo.list_overdue, page=page, page_size=page_size, **extras)
    else:
        items, total = _order_or_400(repo.list_open, page=page, page_size=page_size, **extras)
    return ReceivableListResponse(
        items=[_receivable_to_response(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if page_size else 1,
    )


# ── Expenses ─────────────────────────────────────────


@router.get("/expenses", response_model=ExpenseListResponse)
def list_expenses(
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Busca em description ou notes"),
    date_from: Optional[str] = Query(None, description="Data a partir de YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="Data até YYYY-MM-DD (inclusivo)"),
    order_by: Optional[str] = Query(None, description="date | created_at | amount | category | description"),
    order: Optional[str] = Query(None, description="asc | desc (padrão: desc por date)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    repo = SQLAlchemyExpenseRepository(db, ctx.tenant_id)
    from app.domain.financial.expense import ExpenseStatus

    s = _enum_or_400(ExpenseStatus, status, "status")
    date_start, date_end = _parse_date_bounds(date_from, date_to)
    items, total = _order_or_400(
        repo.list_all,
        status=s,
        page=page,
        page_size=page_size,
        q=q,
        date_from=date_start,
        date_to=date_end,
        order_by=order_by,
        order=order,
    )
    return ExpenseListResponse(
        items=[ExpenseResponse.model_validate(_to_dict(i)) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if page_size else 1,
    )


@router.post("/expenses", response_model=dict)
def register_expense(
    data: ExpenseCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    uc = RegisterExpenseUseCase(
        expense_repo=SQLAlchemyExpenseRepository(db, ctx.tenant_id),
        cash_repo=SQLAlchemyCashMovementRepository(db, ctx.tenant_id),
        ledger_repo=SQLAlchemyFinancialLedgerRepository(db, ctx.tenant_id),
    )
    try:
        result = uc.execute(
            {
                "description": data.description,
                "amount": data.amount,
                "category": data.category,
                "date": data.date,
                "payment_method": data.payment_method,
                "notes": data.notes,
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    expense = result["expense"]
    log_finance_audit(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user_id,
        action="expense.created",
        resource="expense",
        resource_id=str(expense.id),
        after={
            "description": expense.description,
            "amount": expense.amount,
            "category": expense.category,
            "date": expense.date,
            "status": expense.status,
        },
    )
    return {"status": "created", "expense": ExpenseResponse.model_validate(_to_dict(expense))}


@router.post("/expenses/{expense_id}/cancel", response_model=dict)
def cancel_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    repo = SQLAlchemyExpenseRepository(db, ctx.tenant_id)
    existing = repo.get_by_id(expense_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Expense not found")
    expense = repo.cancel(expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    log_finance_audit(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user_id,
        action="expense.cancelled",
        resource="expense",
        resource_id=str(expense_id),
        before={
            "status": existing.status,
            "amount": existing.amount,
            "description": existing.description,
        },
        after={"status": expense.status},
    )
    return {"status": "cancelled", "expense": ExpenseResponse.model_validate(_to_dict(expense))}


# ── Cash Movements ───────────────────────────────────


@router.get("/cash", response_model=CashMovementListResponse)
def list_cash_movements(
    type_filter: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Busca em description ou reference_id"),
    date_from: Optional[str] = Query(None, description="Data a partir de YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="Data até YYYY-MM-DD (inclusivo)"),
    order_by: Optional[str] = Query(None, description="created_at | amount | type | balance_after"),
    order: Optional[str] = Query(None, description="asc | desc (padrão: desc por created_at)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    repo = SQLAlchemyCashMovementRepository(db, ctx.tenant_id)
    from app.domain.financial.cash_movement import CashMovementType

    t = _enum_or_400(CashMovementType, type_filter, "type_filter")
    date_start, date_end = _parse_date_bounds(date_from, date_to)
    items, total = _order_or_400(
        repo.list_all,
        type_filter=t,
        page=page,
        page_size=page_size,
        q=q,
        date_from=date_start,
        date_to=date_end,
        order_by=order_by,
        order=order,
    )
    return CashMovementListResponse(
        items=[CashMovementResponse.model_validate(_to_dict(i)) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if page_size else 1,
    )


@router.get("/cash/balance", response_model=dict)
def get_cash_balance(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    repo = SQLAlchemyCashMovementRepository(db, ctx.tenant_id)
    balance = repo.current_balance()
    return {"balance": balance}


# ── Reports ──────────────────────────────────────────


@router.get("/reports/daily", response_model=DailySummaryResponse)
def daily_report(
    date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    target_date = datetime.fromisoformat(date) if date else datetime.utcnow()
    result = _reports_use_case(db, ctx).daily_summary(target_date)
    return DailySummaryResponse(**result)


@router.get("/reports/period", response_model=PeriodSummaryResponse)
def period_report(
    days: int = Query(30, ge=1, le=365, description="Tamanho do período em dias"),
    date_from: Optional[str] = Query(None, alias="from", description="Início YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, alias="to", description="Fim YYYY-MM-DD (inclusivo)"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Relatório do período: totais, série diária e comparação com o anterior."""
    start, end = _resolve_period(days, date_from, date_to)

    result = _reports_use_case(db, ctx).period_summary(start, end)
    if not result["daily"]:
        raise HTTPException(400, "Período vazio")
    return PeriodSummaryResponse(**result)


def _reports_use_case(db: Session, ctx: TenantContext) -> FinancialReportsUseCase:
    return FinancialReportsUseCase(
        payment_repo=SQLAlchemyPaymentRepository(db, ctx.tenant_id),
        receivable_repo=SQLAlchemyReceivableRepository(db, ctx.tenant_id),
        expense_repo=SQLAlchemyExpenseRepository(db, ctx.tenant_id),
        cash_repo=SQLAlchemyCashMovementRepository(db, ctx.tenant_id),
    )


@router.get("/reports/categories", response_model=CategoryBreakdownResponse)
def categories_report(
    days: int = Query(30, ge=1, le=365, description="Tamanho do período em dias"),
    date_from: Optional[str] = Query(None, alias="from", description="Início YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, alias="to", description="Fim YYYY-MM-DD (inclusivo)"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Despesas ATIVAS por categoria no período (donut da Visão Geral)."""
    start, end = _resolve_period(days, date_from, date_to)
    return CategoryBreakdownResponse(**_reports_use_case(db, ctx).categories_summary(start, end))


@router.get("/reports/methods", response_model=MethodBreakdownResponse)
def methods_report(
    days: int = Query(30, ge=1, le=365, description="Tamanho do período em dias"),
    date_from: Optional[str] = Query(None, alias="from", description="Início YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, alias="to", description="Fim YYYY-MM-DD (inclusivo)"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Pagamentos recebidos (PAID/PARTIAL) por forma no período."""
    start, end = _resolve_period(days, date_from, date_to)
    return MethodBreakdownResponse(**_reports_use_case(db, ctx).methods_summary(start, end))


@router.get("/receivables/summary", response_model=ReceivablesSummaryResponse)
def receivables_summary(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Aging dos recebíveis em aberto: totais + buckets 0-30/31-60/61-90/90+."""
    return ReceivablesSummaryResponse(**_reports_use_case(db, ctx).receivables_summary())


# ── P2 — analytics (dre, products, projection, team, hourly, conciliation) ──


@router.get("/reports/dre", response_model=DreResponse)
def dre_report(
    days: int = Query(30, ge=1, le=365, description="Tamanho do período em dias"),
    date_from: Optional[str] = Query(None, alias="from", description="Início YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, alias="to", description="Fim YYYY-MM-DD (inclusivo)"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """DRE gerencial: receita − CMV ponderado − despesas, com cmv_coverage."""
    from app.application.reports import finance_reports

    start, end = _resolve_period(days, date_from, date_to)
    return DreResponse(**finance_reports.dre(db, ctx.tenant_id, start, end))


@router.get("/reports/products", response_model=ProductsResponse)
def products_report(
    days: int = Query(30, ge=1, le=365, description="Tamanho do período em dias"),
    date_from: Optional[str] = Query(None, alias="from", description="Início YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, alias="to", description="Fim YYYY-MM-DD (inclusivo)"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Margem por produto; sem nota de compra → cost_known=false e margem None."""
    from app.application.reports import finance_reports

    start, end = _resolve_period(days, date_from, date_to)
    return ProductsResponse(**finance_reports.products(db, ctx.tenant_id, start, end))


@router.get("/reports/projection", response_model=ProjectionResponse)
def projection_report(
    horizon: int = Query(30, ge=1, le=180, description="Horizonte em dias (1–180)"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Projeção de caixa: saldo + recebíveis no horizonte − média de despesas (sem ML)."""
    from app.application.reports import finance_reports

    return ProjectionResponse(**finance_reports.projection(db, ctx.tenant_id, horizon))


@router.get("/reports/team", response_model=TeamResponse)
def team_report(
    days: int = Query(30, description="Janela em dias (1, 7, 30, 90 ou 180)"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Entregas por motorista + folha SALARY do período (sem rateio por entregador)."""
    from app.application.reports import finance_reports
    from app.application.reports.delivery_metrics import VALID_DAYS

    if days not in VALID_DAYS:
        raise HTTPException(400, f"Janela inválida: use {list(VALID_DAYS)} dias")
    return TeamResponse(**finance_reports.team(db, ctx.tenant_id, days))


@router.get("/reports/hourly", response_model=HourlyResponse)
def hourly_report(
    days: int = Query(30, ge=1, le=365, description="Tamanho do período em dias"),
    date_from: Optional[str] = Query(None, alias="from", description="Início YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, alias="to", description="Fim YYYY-MM-DD (inclusivo)"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Pagamentos recebidos por hora do dia (paid_at); despesas ficam de fora."""
    from app.application.reports import finance_reports

    start, end = _resolve_period(days, date_from, date_to)
    return HourlyResponse(**finance_reports.hourly(db, ctx.tenant_id, start, end))


@router.get("/reports/conciliation", response_model=ConciliationResponse)
def conciliation_report(
    days: int = Query(30, ge=1, le=365, description="Tamanho do período em dias"),
    date_from: Optional[str] = Query(None, alias="from", description="Início YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, alias="to", description="Fim YYYY-MM-DD (inclusivo)"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Cruza pagamento ↔ caixa ↔ recebível; divergências são 'a revisar'."""
    from app.application.reports import finance_reports

    start, end = _resolve_period(days, date_from, date_to)
    return ConciliationResponse(**finance_reports.conciliation(db, ctx.tenant_id, start, end))


# ── P3 — orçamento mensal (V4: tenant, ano, mês, categoria) ──


@router.get("/budget", response_model=BudgetResponse)
def get_budget(
    year: Optional[int] = Query(None, ge=2020, le=2100, description="Ano do orçamento (padrão: atual)"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Mês 1–12 (padrão: atual)"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Orçamento do mês na tabela finance_budgets; defaults = mês corrente (UTC)."""
    now = datetime.utcnow()
    target_year = year if year is not None else now.year
    target_month = month if month is not None else now.month
    rows = SQLAlchemyFinanceBudgetRepository(db, ctx.tenant_id).list_month(target_year, target_month)
    items = _budget_items(rows)
    return BudgetResponse(
        year=target_year,
        month=target_month,
        items=items,
        total=sum((item.amount for item in items), Decimal("0.00")),
    )


@router.put("/budget", response_model=BudgetResponse)
def put_budget(
    data: BudgetUpsertRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Substitui TODOS os itens do mês (replace-all) e audita antes/depois."""
    entries: list[tuple[str, Decimal]] = []
    seen: set[str] = set()
    for item in data.items:
        category = item.category.strip()
        if not category:
            raise HTTPException(400, "Categoria não pode ser vazia")
        if len(category) > 100:
            raise HTTPException(400, "Categoria muito longa (máx. 100 caracteres)")
        key = category.casefold()
        if key in seen:
            raise HTTPException(400, f"Categoria duplicada: {category}")
        seen.add(key)
        entries.append((category, item.amount))

    repo = SQLAlchemyFinanceBudgetRepository(db, ctx.tenant_id)
    before = _budget_snapshot(repo.list_month(data.year, data.month))
    rows = repo.replace_month(data.year, data.month, entries)
    after = _budget_snapshot(rows)
    log_finance_audit(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user_id,
        action="budget.upserted",
        resource="budget",
        resource_id=f"{data.year}-{data.month:02d}",
        before=before,
        after=after,
    )
    items = _budget_items(rows)
    return BudgetResponse(
        year=data.year,
        month=data.month,
        items=items,
        total=sum((item.amount for item in items), Decimal("0.00")),
    )


# ── P3 — relatórios salvos ────────────────────────────


@router.get("/saved-reports", response_model=SavedReportListResponse)
def list_saved_reports(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    rows = SQLAlchemySavedReportRepository(db, ctx.tenant_id).list_all()
    return SavedReportListResponse(items=[_saved_report_to_response(r) for r in rows], total=len(rows))


@router.post("/saved-reports", response_model=SavedReportResponse)
def create_saved_report(
    data: SavedReportCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    name = data.name.strip()
    report_type = data.report_type.strip()
    if not name:
        raise HTTPException(400, "Nome não pode ser vazio")
    if not report_type:
        raise HTTPException(400, "report_type não pode ser vazio")

    repo = SQLAlchemySavedReportRepository(db, ctx.tenant_id)
    if repo.count() >= 100:
        raise HTTPException(400, "Limite de relatórios salvos atingido (100)")
    if repo.name_exists(name):
        raise HTTPException(400, f"Já existe um relatório salvo chamado {name!r}")

    row = repo.create(
        name=name,
        report_type=report_type,
        params=data.params,
        created_by=ctx.user_id,
    )
    log_finance_audit(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user_id,
        action="saved_report.created",
        resource="saved_report",
        resource_id=str(row.id),
        after={"name": row.name, "report_type": row.report_type},
    )
    return _saved_report_to_response(row)


@router.delete("/saved-reports/{report_id}", response_model=dict)
def delete_saved_report(
    report_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    repo = SQLAlchemySavedReportRepository(db, ctx.tenant_id)
    row = repo.get_by_id(report_id)
    if row is None:
        raise HTTPException(404, "Relatório salvo não encontrado")
    repo.delete(report_id)
    log_finance_audit(
        db,
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user_id,
        action="saved_report.deleted",
        resource="saved_report",
        resource_id=str(report_id),
        before={"name": row.name, "report_type": row.report_type},
    )
    return {"status": "deleted", "id": report_id}


# ── P3 — auditoria financeira ─────────────────────────

FINANCE_AUDIT_RESOURCES = (
    "payment",
    "expense",
    "budget",
    "saved_report",
    "cash_movement",
    "receivable",
)


@router.get("/audit", response_model=FinanceAuditResponse)
def finance_audit(
    days: int = Query(30, ge=1, le=365, description="Janela em dias até agora"),
    limit: int = Query(100, ge=1, le=500, description="Máximo de itens retornados"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("audit.view")),
):
    """Trilha de auditoria financeira (só eventos a partir do deploy — sem backfill)."""
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(AuthAuditModel)
        .filter(
            AuthAuditModel.tenant_id == ctx.tenant_id,
            AuthAuditModel.resource.in_(FINANCE_AUDIT_RESOURCES),
            AuthAuditModel.timestamp >= since,
        )
        .order_by(AuthAuditModel.timestamp.desc(), AuthAuditModel.id)
        .limit(limit)
        .all()
    )
    return FinanceAuditResponse(days=days, total=len(rows), items=[FinanceAuditItem.model_validate(r) for r in rows])


# ── Helpers ──────────────────────────────────────────


def _budget_items(rows: list[FinanceBudgetModel]) -> list[BudgetItem]:
    return [BudgetItem(category=str(row.category), amount=Decimal(str(row.amount))) for row in rows]


def _budget_snapshot(rows: list[FinanceBudgetModel]) -> dict:
    """Snapshot antes/depois do PUT (Decimal serializado pelo audit helper)."""
    return {"items": [{"category": row.category, "amount": row.amount} for row in rows]}


def _saved_report_to_response(row: FinanceSavedReportModel) -> SavedReportResponse:
    return SavedReportResponse.model_validate(row)


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
        status=r.status.value if hasattr(r.status, "value") else r.status,
        created_at=r.created_at,
        settled_at=r.settled_at,
    )
