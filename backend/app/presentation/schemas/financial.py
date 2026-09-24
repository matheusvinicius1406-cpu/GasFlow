"""
Financial Pydantic Schemas — FASE 8

Frontend CANNOT send: remaining_amount, paid_amount, cash_balance, balance_after.
Backend calculates all derived values.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


# ── Payment ──────────────────────────────────────────


class PaymentCreate(BaseModel):
    """Payment creation schema.

    Note: order_codigo is taken from the URL path parameter,
    not required in the body.
    """

    amount: Decimal = Field(..., gt=0, description="Payment amount > 0")
    method: str = Field("CASH", description="CASH, PIX, CARD, TRANSFER, OTHER")
    reference: Optional[str] = None
    idempotency_key: Optional[str] = None
    notes: Optional[str] = None


class PaymentResponse(BaseModel):
    id: int
    order_codigo: str
    amount: Decimal
    method: str
    status: str
    paid_at: Optional[datetime] = None
    reference: Optional[str] = None
    idempotency_key: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Receivable ───────────────────────────────────────


class ReceivableResponse(BaseModel):
    id: int
    customer_codigo: str
    order_codigo: str
    original_amount: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal = Field(description="Derived: original - paid")
    due_date: Optional[datetime] = None
    status: str
    created_at: datetime
    settled_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── Expense ──────────────────────────────────────────


class ExpenseCreate(BaseModel):
    description: str = Field(..., min_length=1)
    amount: Decimal = Field(..., gt=0, description="Expense amount > 0")
    category: str = Field("OTHER")
    date: Optional[datetime] = None
    payment_method: Optional[str] = None
    notes: Optional[str] = None


class ExpenseResponse(BaseModel):
    id: int
    description: str
    amount: Decimal
    category: str
    date: datetime
    payment_method: Optional[str] = None
    notes: Optional[str] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Cash Movement ────────────────────────────────────


class CashMovementResponse(BaseModel):
    id: int
    type: str
    amount: Decimal
    description: str
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    balance_after: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Financial Reports ────────────────────────────────


class DailySummaryResponse(BaseModel):
    date: str
    total_receipts: Decimal
    total_expenses: Decimal
    net_result: Decimal


class PeriodDayResponse(BaseModel):
    date: str
    receipts: Decimal
    expenses: Decimal
    net_result: Decimal


class PeriodTotalsResponse(BaseModel):
    from_date: str = Field(alias="from")
    to_date: str = Field(alias="to")
    total_receipts: Decimal
    total_expenses: Decimal
    net_result: Decimal

    model_config = ConfigDict(populate_by_name=True)


class PeriodComparisonResponse(BaseModel):
    # None quando o período anterior está zerado (a tela mostra "—")
    receipts_pct: Optional[float] = None
    expenses_pct: Optional[float] = None
    net_pct: Optional[float] = None


class PeriodSummaryResponse(BaseModel):
    from_date: str = Field(alias="from")
    to_date: str = Field(alias="to")
    days: int
    total_receipts: Decimal
    total_expenses: Decimal
    net_result: Decimal
    daily: list[PeriodDayResponse]
    previous: PeriodTotalsResponse
    comparison: PeriodComparisonResponse

    model_config = ConfigDict(populate_by_name=True)


class CategoryBreakdownItem(BaseModel):
    category: str
    total: Decimal
    pct: Optional[float] = Field(None, description="% do total do período (None quando total = 0)")


class CategoryBreakdownResponse(BaseModel):
    from_date: str = Field(alias="from")
    to_date: str = Field(alias="to")
    days: int
    total: Decimal
    items: List[CategoryBreakdownItem]

    model_config = ConfigDict(populate_by_name=True)


class MethodBreakdownItem(BaseModel):
    method: str
    total: Decimal
    pct: Optional[float] = Field(None, description="% do total do período (None quando total = 0)")


class MethodBreakdownResponse(BaseModel):
    from_date: str = Field(alias="from")
    to_date: str = Field(alias="to")
    days: int
    total: Decimal
    items: List[MethodBreakdownItem]

    model_config = ConfigDict(populate_by_name=True)


class AgingBucketResponse(BaseModel):
    bucket: str = Field(description="0-30 | 31-60 | 61-90 | 90+ (dias de atraso; não vencidos contam como 0)")
    count: int
    total: Decimal = Field(description="Soma de remaining_amount no bucket")


class ReceivablesSummaryResponse(BaseModel):
    generated_at: datetime
    open_count: int
    open_total: Decimal = Field(description="Soma de remaining_amount em aberto")
    overdue_count: int
    overdue_total: Decimal
    buckets: List[AgingBucketResponse]


# ── P2 — analytics (dre, products, projection, team, hourly, conciliation) ──


class DreExpenseItem(BaseModel):
    category: str
    total: Decimal
    pct: Optional[float] = Field(None, description="% da despesa total do período (None quando total = 0)")


class DreResponse(BaseModel):
    from_date: str = Field(alias="from")
    to_date: str = Field(alias="to")
    days: int
    revenue: Decimal = Field(description="Soma de subtotal dos itens vendidos no período")
    cmv: Decimal = Field(description="CMV ponderado só dos produtos com nota CONFIRMED")
    gross_profit: Decimal
    expenses: Decimal
    result: Decimal
    cmv_coverage: Optional[float] = Field(
        None, description="% da receita com custo conhecido (None quando receita = 0)"
    )
    expense_items: List[DreExpenseItem]

    model_config = ConfigDict(populate_by_name=True)


class ProductMarginItem(BaseModel):
    product_codigo: str
    product_nome: str
    quantity: int
    revenue: Decimal
    unit_cost: Optional[Decimal] = Field(None, description="Custo médio ponderado (None sem nota CONFIRMED)")
    cost_known: bool
    margin: Optional[Decimal] = Field(None, description="revenue − qty×unit_cost (None quando cost_known=false)")
    margin_pct: Optional[float]


class ProductsResponse(BaseModel):
    from_date: str = Field(alias="from")
    to_date: str = Field(alias="to")
    days: int
    revenue: Decimal
    items: List[ProductMarginItem]

    model_config = ConfigDict(populate_by_name=True)


class ProjectionDay(BaseModel):
    date: str
    inflow: Decimal
    outflow: Decimal
    balance: Decimal


class ProjectionResponse(BaseModel):
    generated_at: datetime
    horizon: int
    current_balance: Decimal
    expected_in: Decimal = Field(description="Recebíveis com vencimento até o fim do horizonte")
    avg_daily_expenses: Decimal
    expected_out: Decimal
    projected_balance: Decimal
    daily: List[ProjectionDay]
    model: str = Field(description="Rótulo honesto do modelo (sem ML)")


class TeamDriverItem(BaseModel):
    driver_id: str
    nome: Optional[str] = None
    assigned: int
    delivered: int
    failed: int
    avg_minutes: Optional[float] = None


class TeamResponse(BaseModel):
    days: int
    generated_at: datetime
    by_driver: List[TeamDriverItem]
    salary_total: Decimal
    note: str


class HourlyBucket(BaseModel):
    hour: int = Field(ge=0, le=23)
    count: int
    total: Decimal


class HourlyResponse(BaseModel):
    from_date: str = Field(alias="from")
    to_date: str = Field(alias="to")
    days: int
    buckets: List[HourlyBucket] = Field(description="24 buckets (00–23) por hora de paid_at")
    total: Decimal

    model_config = ConfigDict(populate_by_name=True)


class ConciliationItem(BaseModel):
    payment_id: int
    order_codigo: str
    amount: Decimal
    method: str
    status: str
    has_cash_movement: bool
    receivable_status: Optional[str] = None
    receivable_delta: Optional[Decimal] = Field(None, description="paid_amount − soma de pagamentos (0 = ok)")
    issues: List[str] = Field(
        description="Códigos 'a revisar': sem_movimento_de_caixa | sem_recebivel | recebivel_em_divergencia"
    )


class ConciliationResponse(BaseModel):
    from_date: str = Field(alias="from")
    to_date: str = Field(alias="to")
    days: int
    checked: int
    matched: int
    to_review: int
    items: List[ConciliationItem] = Field(description="Divergências (teto 200); matched não vem item a item")
    note: str

    model_config = ConfigDict(populate_by_name=True)


# ── Paginated responses ─────────────────────────────


class PaymentListResponse(BaseModel):
    items: List[PaymentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ReceivableListResponse(BaseModel):
    items: List[ReceivableResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ExpenseListResponse(BaseModel):
    items: List[ExpenseResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CashMovementListResponse(BaseModel):
    items: List[CashMovementResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
