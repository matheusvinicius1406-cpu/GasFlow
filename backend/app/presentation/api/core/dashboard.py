"""
Dashboard API — GasFlow

Consolidated endpoint for the premium dashboard.
GET /dashboard — Dashboard overview
"""

import logging

from fastapi import APIRouter, Depends
from app.presentation.dependencies import get_tenant_context
from app.domain.security.models import TenantContext

logger = logging.getLogger("gasflow.dashboard")
from typing import Any
from datetime import datetime, date

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _trend(current: float, previous: float) -> dict[str, Any]:
    if previous == 0:
        return {"value": 0, "positive": current >= 0}
    pct = round(((current - previous) / previous) * 100, 1)
    return {"value": abs(pct), "positive": pct >= 0}


def _metricas_pedidos(all_orders: list, today: date) -> tuple[dict[str, Any], list]:
    """Totais, contagens por status e receitas (hoje + acumulado)."""
    total_orders = len(all_orders)
    pending_orders = sum(1 for o in all_orders if o.status == "PENDING")
    confirmed_orders = sum(1 for o in all_orders if o.status == "CONFIRMED")
    delivering_orders = sum(1 for o in all_orders if o.status == "DELIVERING")
    delivered_orders = sum(1 for o in all_orders if o.status == "DELIVERED")

    today_orders = [o for o in all_orders if o.created_at and o.created_at.date() == today]
    total_revenue = sum(float(o.total or 0) for o in all_orders if o.payment_status == "PAID")
    today_revenue = sum(float(o.total or 0) for o in today_orders if o.payment_status == "PAID")
    paid_orders = [o for o in all_orders if o.payment_status == "PAID"]
    avg_ticket = total_revenue / len(paid_orders) if paid_orders else 0

    summary = {
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "confirmed_orders": confirmed_orders,
        "delivering_orders": delivering_orders,
        "delivered_orders": delivered_orders,
        "today_orders": len(today_orders),
        "total_revenue": total_revenue,
        "today_revenue": today_revenue,
        "avg_ticket": avg_ticket,
    }
    return summary, today_orders


def _contagens(db: Any, tid: str) -> dict[str, Any]:
    from sqlalchemy import func
    from app.infrastructure.repositories.client_model import ClientModel
    from app.infrastructure.repositories.product_model import ProductModel
    from app.infrastructure.repositories.delivery_model import DeliveryDriverModel

    total_clients = db.query(func.count(ClientModel.id)).filter(ClientModel.tenant_id == tid).scalar() or 0
    total_products = db.query(func.count(ProductModel.id)).filter(ProductModel.tenant_id == tid).scalar() or 0
    total_drivers = (
        db.query(func.count(DeliveryDriverModel.id)).filter(DeliveryDriverModel.tenant_id == tid).scalar() or 0
    )
    return {"clients": total_clients, "products": total_products, "drivers": total_drivers}


def _resumo_pagamentos(db: Any, tid: str, today: date) -> dict[str, Any]:
    from app.infrastructure.repositories.financial_models import PaymentModel

    all_payments = db.query(PaymentModel).filter(PaymentModel.tenant_id == tid).all()
    total_received = sum(float(p.amount or 0) for p in all_payments if p.status == "PAID")
    total_pending = sum(float(p.amount or 0) for p in all_payments if p.status == "PENDING")
    today_received = sum(
        float(p.amount or 0) for p in all_payments if p.status == "PAID" and p.paid_at and p.paid_at.date() == today
    )
    return {"total_received": total_received, "total_pending": total_pending, "today_received": today_received}


def _resumo_despesas(db: Any, tid: str, today: date) -> dict[str, Any]:
    from app.infrastructure.repositories.financial_models import ExpenseModel

    all_expenses = db.query(ExpenseModel).filter(ExpenseModel.tenant_id == tid).all()
    active_expenses = [e for e in all_expenses if e.status == "ACTIVE"]
    total_expenses = sum(float(e.amount or 0) for e in active_expenses)
    today_expenses = sum(float(e.amount or 0) for e in active_expenses if e.date and e.date == today)
    return {"total_expenses": total_expenses, "today_expenses": today_expenses}


def _saldo_caixa(db: Any, tid: str) -> float:
    from app.infrastructure.repositories.financial_models import CashMovementModel

    cash_balance: float = 0
    try:
        last_cash = (
            db.query(CashMovementModel)
            .filter(CashMovementModel.tenant_id == tid)
            .order_by(CashMovementModel.id.desc())
            .first()
        )
        if last_cash:
            cash_balance = float(last_cash.balance_after or 0)
    except Exception:
        # Métrica cosmética do dashboard — falha não pode derrubar a página.
        logger.debug("dashboard.cash_balance_failed", exc_info=True)
    return cash_balance


def _resumo_estoque(db: Any, tid: str) -> tuple[dict[str, Any], list, list]:
    from app.infrastructure.repositories.inventory_model import InventoryModel

    inventory_items = db.query(InventoryModel).filter(InventoryModel.tenant_id == tid).all()
    # InventoryModel não tem coluna stock_status — deriva de quantity vs mínimo.
    # (Bug latente: qualquer linha de estoque quebrava o /dashboard com AttributeError.)
    low_stock = [i for i in inventory_items if i.quantity > 0 and i.quantity <= (i.minimum_quantity or 0)]
    out_of_stock = [i for i in inventory_items if i.quantity <= 0]
    section = {
        "total_items": len(inventory_items),
        "low_stock_count": len(low_stock),
        "out_of_stock_count": len(out_of_stock),
        "low_stock_products": [
            {"product_codigo": i.product_codigo, "quantity": i.quantity, "minimum": i.minimum_quantity}
            for i in low_stock[:5]
        ],
    }
    return section, low_stock, out_of_stock


def _tendencias(
    db: Any, tid: str, today: date, all_orders: list, today_orders: list, summary: dict, pagamentos: dict
) -> dict[str, Any]:
    from app.infrastructure.repositories.financial_models import PaymentModel

    yesterday = today - __import__("datetime").timedelta(days=1)
    yesterday_orders = [o for o in all_orders if o.created_at and o.created_at.date() == yesterday]
    yesterday_revenue = sum(float(o.total or 0) for o in yesterday_orders if o.payment_status == "PAID")
    _yesterday_delivered = sum(
        1 for o in all_orders if o.status == "DELIVERED" and o.updated_at and o.updated_at.date() == yesterday
    )

    yesterday_payments = db.query(PaymentModel).filter(PaymentModel.tenant_id == tid).all()
    yesterday_received = sum(
        float(p.amount or 0)
        for p in yesterday_payments
        if p.status == "PAID" and p.paid_at and p.paid_at.date() == yesterday
    )

    return {
        "today_orders": _trend(len(today_orders), len(yesterday_orders)),
        "today_revenue": _trend(summary["today_revenue"], yesterday_revenue),
        # Sem trend de "Em Rota": o schema atual não guarda histórico de
        # entregas em rota, então comparar com 0 fabricaria um indicador
        # sem sentido. O FE omite o chip quando a chave está ausente.
        "today_received": _trend(pagamentos["today_received"], yesterday_received),
    }


def _distribuicao_horaria(today_orders: list) -> list[dict[str, Any]]:
    hourly = [0] * 24
    for o in today_orders:
        if o.created_at:
            hourly[o.created_at.hour] += 1
    return [
        {"hour": h, "count": hourly[h]}
        for h in range(6, 23)  # 06:00–22:00
    ]


def _entregas_ativas(db: Any, tid: str, all_orders: list) -> list[dict[str, Any]]:
    from app.infrastructure.repositories.delivery_model import DeliveryDriverModel

    delivering_list = [o for o in all_orders if o.status == "DELIVERING"]
    active_deliveries = []
    for o in delivering_list[:10]:
        driver_name = None
        driver_phone = None
        if o.delivery_driver_codigo:
            try:
                driver = (
                    db.query(DeliveryDriverModel)
                    .filter(
                        DeliveryDriverModel.tenant_id == tid, DeliveryDriverModel.codigo == o.delivery_driver_codigo
                    )
                    .first()
                )
                if driver:
                    driver_name = driver.name
                    driver_phone = getattr(driver, "phone", None)
            except Exception:
                logger.debug("dashboard.driver_lookup_failed", exc_info=True)
        active_deliveries.append(
            {
                "order_codigo": o.codigo,
                "client_codigo": o.client_codigo,
                "total": float(o.total or 0),
                "driver_codigo": o.delivery_driver_codigo,
                "driver_name": driver_name,
                "driver_phone": driver_phone,
                "updated_at": o.updated_at.isoformat() if o.updated_at else None,
            }
        )
    return active_deliveries


def _pedidos_recentes(all_orders: list) -> list[dict[str, Any]]:
    recent = sorted(all_orders, key=lambda o: o.created_at or datetime.min, reverse=True)[:5]
    return [
        {
            "codigo": o.codigo,
            "client_codigo": o.client_codigo,
            "total": float(o.total or 0),
            "status": o.status,
            "payment_status": o.payment_status,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in recent
    ]


def _alertas(summary: dict, low_stock: list, out_of_stock: list) -> list[dict[str, Any]]:
    pending_orders = summary["pending_orders"]
    delivering_orders = summary["delivering_orders"]
    alerts = []
    if pending_orders > 0:
        alerts.append(
            {
                "type": "warning",
                "title": f"{pending_orders} pedido{'s' if pending_orders > 1 else ''} pendente{'s' if pending_orders > 1 else ''}",
                "description": "Pedidos aguardando processamento",
                "action": "/orders",
            }
        )
    if out_of_stock:
        alerts.append(
            {
                "type": "danger",
                "title": f"{len(out_of_stock)} produto{'s' if len(out_of_stock) > 1 else ''} sem estoque",
                "description": "Produtos com estoque zerado",
                "action": "/inventory",
            }
        )
    if low_stock:
        alerts.append(
            {
                "type": "warning",
                "title": f"{len(low_stock)} produto{'s' if len(low_stock) > 1 else ''} com estoque baixo",
                "description": "Considere repor o estoque",
                "action": "/inventory",
            }
        )
    if delivering_orders > 0:
        alerts.append(
            {
                "type": "info",
                "title": f"{delivering_orders} entrega{'s' if delivering_orders > 1 else ''} em rota",
                "description": "Entregas em andamento",
                "action": "/deliveries",
            }
        )
    return alerts


@router.get("")
async def get_dashboard(ctx: TenantContext = Depends(get_tenant_context)) -> dict[str, Any]:
    """Get consolidated dashboard data."""
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.order_model import OrderModel

    db = DBSession(bind=engine)
    tid = ctx.tenant_id
    try:
        today = date.today()

        # ── Orders ──────────────────────────────────────────
        all_orders = db.query(OrderModel).filter(OrderModel.tenant_id == tid).all()
        summary, today_orders = _metricas_pedidos(all_orders, today)

        # ── Counts ──────────────────────────────────────────
        counts = _contagens(db, tid)

        # ── Payments / Expenses / Cash Balance ──────────────
        pagamentos = _resumo_pagamentos(db, tid, today)
        despesas = _resumo_despesas(db, tid, today)
        caixa = _saldo_caixa(db, tid)

        # ── Inventory ───────────────────────────────────────
        inventory, low_stock, out_of_stock = _resumo_estoque(db, tid)

        # ── Yesterday Comparison (Trends) ──────────────────
        trends = _tendencias(db, tid, today, all_orders, today_orders, summary, pagamentos)

        # ── Hourly Distribution (Today) ────────────────────
        hourly_data = _distribuicao_horaria(today_orders)

        # ── Active Deliveries ──────────────────────────────
        active_deliveries = _entregas_ativas(db, tid, all_orders)

        # ── Recent Orders ───────────────────────────────────
        recent_orders = _pedidos_recentes(all_orders)

        # ── Result ──────────────────────────────────────────
        result = pagamentos["total_received"] - despesas["total_expenses"]

        # ── Alerts ──────────────────────────────────────────
        alerts = _alertas(summary, low_stock, out_of_stock)

        return {
            "summary": summary,
            "clients": {"total": counts["clients"]},
            "products": {"total": counts["products"]},
            "drivers": {"total": counts["drivers"]},
            "financial": {
                "total_received": pagamentos["total_received"],
                "today_received": pagamentos["today_received"],
                "total_pending": pagamentos["total_pending"],
                "total_expenses": despesas["total_expenses"],
                "today_expenses": despesas["today_expenses"],
                "cash_balance": caixa,
                "result": result,
            },
            "inventory": inventory,
            "trends": trends,
            "hourly_orders": hourly_data,
            "active_deliveries": active_deliveries,
            "recent_orders": recent_orders,
            "alerts": alerts,
            "generated_at": datetime.now().isoformat(),
        }
    finally:
        db.close()
