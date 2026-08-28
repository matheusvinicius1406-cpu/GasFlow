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
    """Get order data for a specific date from the delivery ops store."""
    try:
        from app.presentation.api.delivery_ops import _get_store
        store = _get_store()

        orders = []
        payments = []
        expenses = []

        # Get deliveries (which contain order data)
        for delivery in store.get("deliveries", {}).values():
            if hasattr(delivery, 'tenant_id') and delivery.tenant_id == tenant_id:
                order_data = {
                    "codigo": getattr(delivery, 'order_id', '???'),
                    "client_name": getattr(delivery, 'customer_name', ''),
                    "customer_codigo": getattr(delivery, 'customer_codigo', ''),
                    "status": getattr(delivery, 'status', 'PENDING').value if hasattr(getattr(delivery, 'status', None), 'value') else str(getattr(delivery, 'status', 'PENDING')),
                    "total": 0,
                    "items": [],
                    "created_at": getattr(delivery, 'created_at', ''),
                    "payment_method": "",
                }
                orders.append(order_data)

        return orders, payments, expenses
    except Exception:
        return [], [], []


@router.get("/daily")
async def get_daily_report(
    date: Optional[str] = Query(None, description="Report date (YYYY-MM-DD)"),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get daily report summary as JSON."""
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')

    # Validate date format
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")

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
        date = datetime.now().strftime('%Y-%m-%d')

    # Validate date format
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")

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
        from app.presentation.api.delivery_ops import _get_store
        store = _get_store()

        deliveries = list(store.get("deliveries", {}).values())
        drivers = list(store.get("drivers", {}).values())

        # Filter by tenant
        deliveries = [d for d in deliveries if hasattr(d, 'tenant_id') and d.tenant_id == ctx.tenant_id]
        drivers = [d for d in drivers if hasattr(d, 'tenant_id') and d.tenant_id == ctx.tenant_id]

        total_deliveries = len(deliveries)
        delivered = sum(1 for d in deliveries if hasattr(d, 'status') and
                        (d.status.value if hasattr(d.status, 'value') else str(d.status)) == 'DELIVERED')
        failed = sum(1 for d in deliveries if hasattr(d, 'status') and
                     (d.status.value if hasattr(d.status, 'value') else str(d.status)) == 'FAILED')
        active_drivers = sum(1 for d in drivers if hasattr(d, 'is_available') and d.is_available)

        return {
            "total_deliveries": total_deliveries,
            "delivered": delivered,
            "failed": failed,
            "pending": total_deliveries - delivered - failed,
            "total_drivers": len(drivers),
            "active_drivers": active_drivers,
        }
    except Exception:
        return {
            "total_deliveries": 0,
            "delivered": 0,
            "failed": 0,
            "pending": 0,
            "total_drivers": 0,
            "active_drivers": 0,
        }
