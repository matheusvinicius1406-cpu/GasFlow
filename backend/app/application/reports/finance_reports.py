"""
Finance Analytics Reports — P2 da Central Financeira.

Agregações aditivas para os 6 endpoints GET /finance/reports/{dre,products,
projection,team,hourly,conciliation}. Toda query filtra por tenant; valores
monetários saem como Decimal quantizado em 0.01 (ROUND_HALF_UP).

Decisões de honestidade (Fase 2 §3):
- DRE: CMV ponderado só sobre produtos com nota CONFIRMED — `cmv_coverage`
  informa quanto da receita tem custo conhecido; sem nota, CMV não inventa.
- Produtos: sem nota de compra, `cost_known: false` e margem `None`.
- Projeção: saldo + recebíveis com vencimento no horizonte + média diária
  de despesas (30 dias) — modelo declarado, sem ML.
- Equipe: entregas = delivery_metrics; folha = despesas SALARY do período
  (total, sem rateio por entregador).
- Conciliação: divergências são "a revisar", nunca "erro".
"""

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.infrastructure.repositories.delivery_model import DeliveryDriverModel
from app.infrastructure.repositories.financial_models import (
    CashMovementModel,
    ExpenseModel,
    PaymentModel,
    ReceivableModel,
)
from app.infrastructure.repositories.order_item_model import OrderItemModel
from app.infrastructure.repositories.order_model import OrderModel
from app.infrastructure.repositories.purchase_note_model import PurchaseNoteItemModel, PurchaseNoteModel

CENT = Decimal("100")
ZERO = Decimal("0.00")


def _q(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _pct(part: Decimal, total: Decimal) -> Optional[float]:
    if total == 0:
        return None
    return float((part / total * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _period_meta(start: datetime, end: datetime) -> Dict[str, Any]:
    return {
        "from": start.date().isoformat(),
        "to": (end - timedelta(days=1)).date().isoformat(),
        "days": (end - start).days,
    }


# ── Custos de compra (notas CONFIRMED) ──────────────────────────────


def _unit_costs_by_product(db: Session, tenant_id: str) -> Dict[str, Decimal]:
    """Custo médio ponderado (R$/unid.) por produto — notas CONFIRMED."""
    rows = (
        db.query(
            PurchaseNoteItemModel.product_codigo,
            func.sum(PurchaseNoteItemModel.quantity),
            func.sum(PurchaseNoteItemModel.subtotal_cents),
        )
        .join(PurchaseNoteModel, PurchaseNoteModel.id == PurchaseNoteItemModel.purchase_note_id)
        .filter(
            PurchaseNoteModel.tenant_id == tenant_id,
            PurchaseNoteModel.status == "CONFIRMED",
        )
        .group_by(PurchaseNoteItemModel.product_codigo)
        .all()
    )
    costs: Dict[str, Decimal] = {}
    for codigo, qty, subtotal_cents in rows:
        if qty and int(qty) > 0:
            costs[codigo] = _q(Decimal(int(subtotal_cents or 0)) / Decimal(int(qty)) / CENT)
    return costs


def _sold_items_in_period(
    db: Session, tenant_id: str, start: datetime, end: datetime
) -> List[Tuple[str, str, int, Decimal]]:
    """Itens vendidos em pedidos criados no período: (código, nome, qtd, receita)."""
    rows = (
        db.query(
            OrderItemModel.product_codigo,
            func.max(OrderItemModel.product_nome),
            func.sum(OrderItemModel.quantity),
            func.sum(OrderItemModel.subtotal),
        )
        .join(
            OrderModel,
            (OrderModel.codigo == OrderItemModel.order_codigo) & (OrderModel.tenant_id == OrderItemModel.tenant_id),
        )
        .filter(
            OrderItemModel.tenant_id == tenant_id,
            OrderModel.created_at >= start,
            OrderModel.created_at < end,
        )
        .group_by(OrderItemModel.product_codigo)
        .all()
    )
    return [(codigo, nome or codigo, int(qty or 0), _q(revenue or 0)) for codigo, nome, qty, revenue in rows]


# ── 1. DRE ──────────────────────────────────────────────────────────


def dre(db: Session, tenant_id: str, start: datetime, end: datetime) -> Dict[str, Any]:
    """DRE gerencial: receita (itens vendidos) − CMV ponderado − despesas."""
    costs = _unit_costs_by_product(db, tenant_id)
    sold = _sold_items_in_period(db, tenant_id, start, end)

    revenue = ZERO
    revenue_with_cost = ZERO
    cmv = ZERO
    for codigo, _nome, qty, item_revenue in sold:
        revenue += item_revenue
        unit = costs.get(codigo)
        if unit is not None:
            revenue_with_cost += item_revenue
            cmv += _q(Decimal(qty) * unit)
    cmv = _q(cmv)
    gross_profit = _q(revenue - cmv)

    expense_rows = (
        db.query(ExpenseModel.category, func.coalesce(func.sum(ExpenseModel.amount), 0))
        .filter(
            ExpenseModel.tenant_id == tenant_id,
            ExpenseModel.status == "ACTIVE",
            ExpenseModel.date >= start,
            ExpenseModel.date < end,
        )
        .group_by(ExpenseModel.category)
        .all()
    )
    expense_items = sorted(
        ({"category": cat, "total": _q(total)} for cat, total in expense_rows),
        key=lambda item: item["total"],
        reverse=True,
    )
    total_expenses = _q(sum((item["total"] for item in expense_items), ZERO))
    for item in expense_items:
        item["pct"] = _pct(item["total"], total_expenses)

    return {
        **_period_meta(start, end),
        "revenue": _q(revenue),
        "cmv": cmv,
        "gross_profit": gross_profit,
        "expenses": total_expenses,
        "result": _q(gross_profit - total_expenses),
        "cmv_coverage": _pct(revenue_with_cost, revenue),
        "expense_items": expense_items,
    }


# ── 2. Produtos ─────────────────────────────────────────────────────


def products(db: Session, tenant_id: str, start: datetime, end: datetime) -> Dict[str, Any]:
    """Margem por produto no período; sem nota de compra → cost_known false."""
    costs = _unit_costs_by_product(db, tenant_id)
    sold = _sold_items_in_period(db, tenant_id, start, end)

    items: List[Dict[str, Any]] = []
    total_revenue = ZERO
    for codigo, nome, qty, revenue in sold:
        unit = costs.get(codigo)
        cost_known = unit is not None
        margin: Optional[Decimal] = None
        margin_pct: Optional[float] = None
        if unit is not None:
            cogs = _q(Decimal(qty) * unit)
            margin = _q(revenue - cogs)
            margin_pct = _pct(margin, revenue)
        total_revenue += revenue
        items.append(
            {
                "product_codigo": codigo,
                "product_nome": nome,
                "quantity": qty,
                "revenue": revenue,
                "unit_cost": unit,
                "cost_known": cost_known,
                "margin": margin,
                "margin_pct": margin_pct,
            }
        )
    items.sort(key=lambda item: item["revenue"], reverse=True)
    return {**_period_meta(start, end), "revenue": _q(total_revenue), "items": items}


# ── 3. Projeção de caixa ────────────────────────────────────────────


def projection(db: Session, tenant_id: str, horizon: int, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Saldo atual + recebíveis vencendo no horizonte − média de despesas.

    Modelo declarado (sem ML): recebíveis entram no dia do vencimento;
    despesas saem em fatia diária igual da média dos últimos 30 dias.
    Recebíveis sem `due_date` ficam fora da projeção.
    """
    now = now or datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    horizon_end = today + timedelta(days=horizon)

    last_movement = (
        db.query(CashMovementModel)
        .filter(CashMovementModel.tenant_id == tenant_id)
        .order_by(CashMovementModel.id.desc())
        .first()
    )
    current_balance = _q(last_movement.balance_after) if last_movement else ZERO

    open_receivables = (
        db.query(ReceivableModel)
        .filter(
            ReceivableModel.tenant_id == tenant_id,
            ReceivableModel.status.in_(["OPEN", "PARTIAL", "OVERDUE"]),
            ReceivableModel.due_date.isnot(None),
            func.date(ReceivableModel.due_date) <= horizon_end.date(),
        )
        .all()
    )

    hist_start = today - timedelta(days=30)
    expenses_30d = (
        db.query(func.coalesce(func.sum(ExpenseModel.amount), 0))
        .filter(
            ExpenseModel.tenant_id == tenant_id,
            ExpenseModel.status == "ACTIVE",
            ExpenseModel.date >= hist_start,
            ExpenseModel.date < today + timedelta(days=1),
        )
        .scalar()
    )
    avg_daily_expenses = _q(Decimal(str(expenses_30d or 0)) / Decimal(30))

    inflows_by_day: Dict[date, Decimal] = {}
    expected_in = ZERO
    first_day = (today + timedelta(days=1)).date()
    for r in open_receivables:
        remaining = _q(r.original_amount - r.paid_amount)
        if remaining <= 0:
            continue
        # Vencido entra no 1º dia do horizonte (recebimento imediato),
        # senão o saldo diário não bate com expected_in.
        due = r.due_date.date()
        if due < first_day:
            due = first_day
        inflows_by_day[due] = _q(inflows_by_day.get(due, ZERO) + remaining)
        expected_in += remaining
    expected_in = _q(expected_in)

    daily = []
    running = current_balance
    for i in range(1, horizon + 1):
        day = today + timedelta(days=i)
        inflow = inflows_by_day.get(day.date(), ZERO)
        running = _q(running + inflow - avg_daily_expenses)
        daily.append(
            {
                "date": day.date().isoformat(),
                "inflow": inflow,
                "outflow": avg_daily_expenses,
                "balance": running,
            }
        )
    expected_out = _q(avg_daily_expenses * Decimal(horizon))

    return {
        "generated_at": now,
        "horizon": horizon,
        "current_balance": current_balance,
        "expected_in": expected_in,
        "avg_daily_expenses": avg_daily_expenses,
        "expected_out": expected_out,
        "projected_balance": running,
        "daily": daily,
        "model": (
            "Saldo atual + recebíveis com vencimento no horizonte − média "
            "diária de despesas (últimos 30 dias). Sem previsão de receita "
            "futura; recebíveis sem vencimento ficam de fora."
        ),
    }


# ── 4. Equipe ───────────────────────────────────────────────────────


def team(db: Session, tenant_id: str, days: int) -> Dict[str, Any]:
    """Entregas por motorista (delivery_metrics) + folha SALARY do período."""
    from app.application.reports.delivery_metrics import deliveries_by_driver

    by_driver = deliveries_by_driver(db, tenant_id, days)

    drivers = db.query(DeliveryDriverModel).filter(DeliveryDriverModel.tenant_id == tenant_id).all()
    names: Dict[str, str] = {}
    for d in drivers:
        if d.codigo:
            names[str(d.codigo)] = str(d.nome)
        names[str(d.id)] = str(d.nome)

    since = datetime.utcnow() - timedelta(days=days)
    salary_total = _q(
        db.query(func.coalesce(func.sum(ExpenseModel.amount), 0))
        .filter(
            ExpenseModel.tenant_id == tenant_id,
            ExpenseModel.status == "ACTIVE",
            ExpenseModel.category == "SALARY",
            ExpenseModel.date >= since,
        )
        .scalar()
        or 0
    )

    return {
        "days": days,
        "generated_at": datetime.utcnow(),
        "by_driver": [
            {
                "driver_id": row["driver_id"],
                "nome": names.get(str(row["driver_id"])),
                "assigned": row["assigned"],
                "delivered": row["delivered"],
                "failed": row["failed"],
                "avg_minutes": row["avg_minutes"],
            }
            for row in by_driver
        ],
        "salary_total": salary_total,
        "note": (
            "Entregas com a mesma agregação de /reports/deliveries; "
            "folha é o total de despesas SALARY no período, sem rateio por entregador."
        ),
    }


# ── 5. Hourly ───────────────────────────────────────────────────────


def hourly(db: Session, tenant_id: str, start: datetime, end: datetime) -> Dict[str, Any]:
    """Pagamentos recebidos por hora do dia (paid_at, senão created_at).

    Despesas não têm hora confiável e ficam de fora — só a receita.
    """
    ts = func.coalesce(PaymentModel.paid_at, PaymentModel.created_at)
    rows = (
        db.query(
            func.strftime("%H", ts),
            func.count(PaymentModel.id),
            func.coalesce(func.sum(PaymentModel.amount), 0),
        )
        .filter(
            PaymentModel.tenant_id == tenant_id,
            PaymentModel.status.in_(["PAID", "PARTIAL"]),
            ts >= start,
            ts < end,
        )
        .group_by(func.strftime("%H", ts))
        .all()
    )
    by_hour = {int(h): (int(c), _q(total)) for h, c, total in rows if h is not None}
    buckets = []
    total = ZERO
    for h in range(24):
        count, bucket_total = by_hour.get(h, (0, ZERO))
        total += bucket_total
        buckets.append({"hour": h, "count": count, "total": bucket_total})
    return {**_period_meta(start, end), "buckets": buckets, "total": _q(total)}


# ── 6. Conciliação ──────────────────────────────────────────────────

_CONCILIATION_ITEM_CAP = 200


def conciliation(db: Session, tenant_id: str, start: datetime, end: datetime) -> Dict[str, Any]:
    """Cruza pagamento ↔ movimento de caixa ↔ recebível no período.

    Itens divergentes saem com códigos em `issues` (semântica "a revisar").
    """
    ts = func.coalesce(PaymentModel.paid_at, PaymentModel.created_at)
    payments = (
        db.query(PaymentModel)
        .filter(
            PaymentModel.tenant_id == tenant_id,
            PaymentModel.status.in_(["PAID", "PARTIAL", "REFUNDED"]),
            ts >= start,
            ts < end,
        )
        .order_by(PaymentModel.id)
        .all()
    )
    payment_ids = [str(p.id) for p in payments]
    cash_refs: set = set()
    if payment_ids:
        cash_rows = (
            db.query(CashMovementModel.reference_type, CashMovementModel.reference_id)
            .filter(
                CashMovementModel.tenant_id == tenant_id,
                CashMovementModel.reference_type.in_(["PAYMENT", "REFUND"]),
                CashMovementModel.reference_id.in_(payment_ids),
            )
            .all()
        )
        cash_refs = {(ref_type, ref_id) for ref_type, ref_id in cash_rows}

    order_codigos = {str(p.order_codigo) for p in payments}
    receivables: Dict[str, ReceivableModel] = {}
    paid_sums: Dict[str, Decimal] = {}
    if order_codigos:
        for r in (
            db.query(ReceivableModel)
            .filter(
                ReceivableModel.tenant_id == tenant_id,
                ReceivableModel.order_codigo.in_(order_codigos),
            )
            .all()
        ):
            receivables[str(r.order_codigo)] = r
        paid_rows = (
            db.query(PaymentModel.order_codigo, func.coalesce(func.sum(PaymentModel.amount), 0))
            .filter(
                PaymentModel.tenant_id == tenant_id,
                PaymentModel.status.in_(["PAID", "PARTIAL"]),
                PaymentModel.order_codigo.in_(order_codigos),
            )
            .group_by(PaymentModel.order_codigo)
            .all()
        )
        for codigo, total in paid_rows:
            paid_sums[str(codigo)] = _q(total)

    matched = 0
    review_items: List[Dict[str, Any]] = []
    for p in payments:
        issues: List[str] = []
        order_codigo = str(p.order_codigo)
        expected_type = "REFUND" if p.status == "REFUNDED" else "PAYMENT"
        if (expected_type, str(p.id)) not in cash_refs:
            issues.append("sem_movimento_de_caixa")

        receivable = receivables.get(order_codigo)
        receivable_status = str(receivable.status) if receivable else None
        receivable_delta = None
        if receivable is None:
            issues.append("sem_recebivel")
        else:
            receivable_delta = _q(receivable.paid_amount - paid_sums.get(order_codigo, ZERO))
            if receivable_delta != ZERO:
                issues.append("recebivel_em_divergencia")

        if not issues:
            matched += 1
        elif len(review_items) < _CONCILIATION_ITEM_CAP:
            review_items.append(
                {
                    "payment_id": p.id,
                    "order_codigo": order_codigo,
                    "amount": _q(p.amount),
                    "method": str(p.method),
                    "status": str(p.status),
                    "has_cash_movement": "sem_movimento_de_caixa" not in issues,
                    "receivable_status": receivable_status,
                    "receivable_delta": receivable_delta,
                    "issues": issues,
                }
            )

    checked = len(payments)
    return {
        **_period_meta(start, end),
        "checked": checked,
        "matched": matched,
        "to_review": checked - matched,
        "items": review_items,
        "note": (
            "Divergências ficam para revisar — não indicam falha no lançamento. "
            "Confira caixa/recebível antes de ajustar qualquer registro."
        ),
    }
