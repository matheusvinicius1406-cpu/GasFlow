"""
Dashboard API — GasFlow

Consolidated endpoint for the premium dashboard.
GET /dashboard — Dashboard overview
"""

from fastapi import APIRouter, Depends
from app.presentation.dependencies import get_tenant_context
from app.domain.security.models import TenantContext
from typing import Any
from datetime import datetime, date

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(ctx: TenantContext = Depends(get_tenant_context)) -> dict[str, Any]:
    """Get consolidated dashboard data."""
    from sqlalchemy.orm import Session as DBSession
    from sqlalchemy import func
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.order_model import OrderModel
    from app.infrastructure.repositories.client_model import ClientModel
    from app.infrastructure.repositories.product_model import ProductModel
    from app.infrastructure.repositories.financial_models import PaymentModel, ExpenseModel, CashMovementModel
    from app.infrastructure.repositories.delivery_model import DeliveryDriverModel
    from app.infrastructure.repositories.inventory_model import InventoryModel

    db = DBSession(bind=engine)
    tid = ctx.tenant_id
    try:
        today = date.today()

        # ── Orders ──────────────────────────────────────────
        all_orders = db.query(OrderModel).filter(OrderModel.tenant_id == tid).all()
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

        # ── Counts ──────────────────────────────────────────
        total_clients = db.query(func.count(ClientModel.id)).filter(ClientModel.tenant_id == tid).scalar() or 0
        total_products = db.query(func.count(ProductModel.id)).filter(ProductModel.tenant_id == tid).scalar() or 0
        total_drivers = (
            db.query(func.count(DeliveryDriverModel.id)).filter(DeliveryDriverModel.tenant_id == tid).scalar() or 0
        )

        # ── Payments ────────────────────────────────────────
        all_payments = db.query(PaymentModel).filter(PaymentModel.tenant_id == tid).all()
        total_received = sum(float(p.amount or 0) for p in all_payments if p.status == "PAID")
        total_pending_payments = sum(float(p.amount or 0) for p in all_payments if p.status == "PENDING")
        today_received = sum(
            float(p.amount or 0) for p in all_payments if p.status == "PAID" and p.paid_at and p.paid_at.date() == today
        )

        # ── Expenses ────────────────────────────────────────
        all_expenses = db.query(ExpenseModel).filter(ExpenseModel.tenant_id == tid).all()
        active_expenses = [e for e in all_expenses if e.status == "ACTIVE"]
        total_expenses = sum(float(e.amount or 0) for e in active_expenses)
        today_expenses = sum(float(e.amount or 0) for e in active_expenses if e.date and e.date == today)

        # ── Cash Balance ────────────────────────────────────
        cash_balance = 0
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
            pass

        # ── Inventory ───────────────────────────────────────
        inventory_items = db.query(InventoryModel).filter(InventoryModel.tenant_id == tid).all()
        low_stock = [i for i in inventory_items if i.stock_status == "LOW_STOCK"]
        out_of_stock = [i for i in inventory_items if i.stock_status == "OUT_OF_STOCK"]

        # ── Yesterday Comparison (Trends) ──────────────────
        yesterday = today - __import__("datetime").timedelta(days=1)
        yesterday_orders = [o for o in all_orders if o.created_at and o.created_at.date() == yesterday]
        yesterday_revenue = sum(float(o.total or 0) for o in yesterday_orders if o.payment_status == "PAID")
        yesterday_delivered = sum(
            1 for o in all_orders if o.status == "DELIVERED" and o.updated_at and o.updated_at.date() == yesterday
        )

        yesterday_payments = db.query(PaymentModel).filter(PaymentModel.tenant_id == tid).all()
        yesterday_received = sum(
            float(p.amount or 0)
            for p in yesterday_payments
            if p.status == "PAID" and p.paid_at and p.paid_at.date() == yesterday
        )

        def _trend(current: float, previous: float) -> dict[str, Any]:
            if previous == 0:
                return {"value": 0, "positive": current >= 0}
            pct = round(((current - previous) / previous) * 100, 1)
            return {"value": abs(pct), "positive": pct >= 0}

        trends = {
            "today_orders": _trend(len(today_orders), len(yesterday_orders)),
            "today_revenue": _trend(today_revenue, yesterday_revenue),
            # Sem trend de "Em Rota": o schema atual não guarda histórico de
            # entregas em rota, então comparar com 0 fabricaria um indicador
            # sem sentido. O FE omite o chip quando a chave está ausente.
            "today_received": _trend(today_received, yesterday_received),
        }

        # ── Hourly Distribution (Today) ────────────────────
        hourly = [0] * 24
        for o in today_orders:
            if o.created_at:
                hourly[o.created_at.hour] += 1
        hourly_data = [
            {"hour": h, "count": hourly[h]}
            for h in range(6, 23)  # 06:00–22:00
        ]

        # ── Active Deliveries ──────────────────────────────
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
                    pass
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

        # ── Recent Orders ───────────────────────────────────
        recent = sorted(all_orders, key=lambda o: o.created_at or datetime.min, reverse=True)[:5]
        recent_orders = [
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

        # ── Result ──────────────────────────────────────────
        result = total_received - total_expenses

        # ── Alerts ──────────────────────────────────────────
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

        return {
            "summary": {
                "total_orders": total_orders,
                "pending_orders": pending_orders,
                "confirmed_orders": confirmed_orders,
                "delivering_orders": delivering_orders,
                "delivered_orders": delivered_orders,
                "today_orders": len(today_orders),
                "total_revenue": total_revenue,
                "today_revenue": today_revenue,
                "avg_ticket": avg_ticket,
            },
            "clients": {"total": total_clients},
            "products": {"total": total_products},
            "drivers": {"total": total_drivers},
            "financial": {
                "total_received": total_received,
                "today_received": today_received,
                "total_pending": total_pending_payments,
                "total_expenses": total_expenses,
                "today_expenses": today_expenses,
                "cash_balance": cash_balance,
                "result": result,
            },
            "inventory": {
                "total_items": len(inventory_items),
                "low_stock_count": len(low_stock),
                "out_of_stock_count": len(out_of_stock),
                "low_stock_products": [
                    {"product_codigo": i.product_codigo, "quantity": i.quantity, "minimum": i.minimum_quantity}
                    for i in low_stock[:5]
                ],
            },
            "trends": trends,
            "hourly_orders": hourly_data,
            "active_deliveries": active_deliveries,
            "recent_orders": recent_orders,
            "alerts": alerts,
            "generated_at": datetime.now().isoformat(),
        }
    finally:
        db.close()
