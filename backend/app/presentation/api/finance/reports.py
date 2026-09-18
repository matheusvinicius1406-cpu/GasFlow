"""
Reports API — GasFlow

Endpoints for business reports and PDF export.

Endpoints:
    GET /reports/daily — Daily report summary (JSON)
    GET /reports/daily.pdf — Daily report as PDF download
    GET /reports/summary — Business summary
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import Response
from app.presentation.dependencies import get_tenant_context
from app.domain.security.models import TenantContext
from typing import Optional
from datetime import datetime

from app.infrastructure.pdf.daily_report import DailyReportPDF, build_daily_report_data

router = APIRouter(prefix="/reports", tags=["reports"])


def _get_order_data_for_date(tenant_id: str, date: str):
    """Get order data for a specific date from the database."""
    try:
        from sqlalchemy.orm import Session as DBSession
        from app.infrastructure.database.init_db import engine
        from app.infrastructure.repositories.delivery_persistence_repository import (
            SQLAlchemyDeliveryPersistenceRepository,
        )

        orders = []
        payments = []
        expenses = []

        db = DBSession(bind=engine)
        try:
            repo = SQLAlchemyDeliveryPersistenceRepository(db, tenant_id)
            deliveries = repo.list_deliveries(limit=1000)

            for delivery in deliveries:
                order_data = {
                    "codigo": delivery.order_id or "???",
                    "client_name": delivery.customer_name or "",
                    "customer_codigo": delivery.customer_codigo or "",
                    "status": delivery.status or "PENDING",
                    "total": 0,
                    "items": [],
                    "created_at": str(delivery.created_at) if delivery.created_at else "",
                    "payment_method": "",
                }
                orders.append(order_data)
        finally:
            db.close()

        return orders, payments, expenses
    except Exception:
        return [], [], []


@router.get("/heatmap")
async def get_delivery_heatmap(
    days: int = Query(30, description="Período em dias (7, 30 ou 90)"),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Mapa de calor — entregas DELIVERED por bairro no período (F8).

    Agregação SQL por address_neighborhood com cache de 5min; centroide
    aproximado por bairro (bounding box) para a camada de densidade.
    Só visualização (E3) — sempre filtrado por tenant.
    """
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.application.reports.heatmap import delivery_heatmap, VALID_PERIODS

    if days not in VALID_PERIODS:
        raise HTTPException(400, f"Período inválido: use {sorted(VALID_PERIODS)} dias")

    db = DBSession(bind=engine)
    try:
        return delivery_heatmap(db, ctx.tenant_id, days)
    finally:
        db.close()


@router.get("/daily")
async def get_daily_report(
    date: Optional[str] = Query(None, description="Report date (YYYY-MM-DD)"),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get daily report summary as JSON."""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    # Validate date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD") from exc

    # Get data
    orders, payments, expenses = _get_order_data_for_date(ctx.tenant_id, date)

    # Build report data
    report_data = build_daily_report_data(orders, payments, expenses, date)

    return report_data


@router.get("/daily.pdf")
async def get_daily_report_pdf(
    date: Optional[str] = Query(None, description="Report date (YYYY-MM-DD)"),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Download daily report as PDF."""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    # Validate date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD") from exc

    # Get data
    orders, payments, expenses = _get_order_data_for_date(ctx.tenant_id, date)

    # Build report data
    report_data = build_daily_report_data(orders, payments, expenses, date)

    # Generate PDF
    pdf_generator = DailyReportPDF()
    pdf_bytes = pdf_generator.generate(report_data, date)

    # Return as download
    filename = f"relatorio_marcos_gas_{date}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/summary")
async def get_business_summary(
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get business summary across all time."""
    try:
        from sqlalchemy.orm import Session as DBSession
        from app.infrastructure.database.init_db import engine
        from app.infrastructure.repositories.delivery_persistence_repository import (
            SQLAlchemyDeliveryPersistenceRepository,
        )

        db = DBSession(bind=engine)
        try:
            del_repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx.tenant_id)
            status_counts = del_repo.count_by_status()
            total_deliveries = sum(status_counts.values())
            delivered = status_counts.get("DELIVERED", 0)
            failed = status_counts.get("FAILED", 0)
            pending = total_deliveries - delivered - failed

            return {
                "total_deliveries": total_deliveries,
                "delivered": delivered,
                "failed": failed,
                "pending": pending,
                "total_drivers": 0,
                "active_drivers": 0,
            }
        finally:
            db.close()
    except Exception:
        return {
            "total_deliveries": 0,
            "delivered": 0,
            "failed": 0,
            "pending": 0,
            "total_drivers": 0,
            "active_drivers": 0,
        }
