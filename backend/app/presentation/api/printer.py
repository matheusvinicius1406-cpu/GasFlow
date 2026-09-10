"""
Printer API — GasFlow

Endpoints for managing print jobs and printer status.

Endpoints:
    POST /printer/print — Create a print job for an order
    GET /printer/status — Get printer status
    GET /printer/jobs — List print jobs
    GET /printer/jobs/{job_id} — Get specific print job
    POST /printer/jobs/{job_id}/retry — Retry a failed print job
    GET /printer/orders/{order_id}/jobs — Get print jobs for an order
"""

import logging

from fastapi import APIRouter, HTTPException, Depends
from app.presentation.dependencies import get_tenant_context
from app.domain.security.models import TenantContext

logger = logging.getLogger("gasflow.printer")
from pydantic import BaseModel

from app.infrastructure.printing.print_agent import get_print_agent, PrintJobStatus

router = APIRouter(prefix="/printer", tags=["printer"])


class PrintRequest(BaseModel):
    order_id: str
    is_reprint: bool = False


class PrinterStatusResponse(BaseModel):
    status: str
    auto_print_enabled: bool
    pending_jobs: int
    total_jobs_today: int


@router.post("/print")
async def create_print_job(req: PrintRequest, ctx: TenantContext = Depends(get_tenant_context)):
    """Create a print job for an order."""
    agent = get_print_agent()

    # Build order data from available sources
    # In production, this would fetch from the order repository
    order_data = {
        "codigo": req.order_id,
        "client_name": "Cliente",
        "client_address": "Endereco",
        "items": [],
        "total": 0,
        "payment_method": "",
        "notes": "",
        "created_at": "",
    }

    # Try to get real order data from the database
    try:
        from sqlalchemy.orm import Session as DBSession
        from app.infrastructure.database.init_db import engine
        from app.infrastructure.repositories.delivery_persistence_repository import (
            SQLAlchemyDeliveryPersistenceRepository,
        )

        db = DBSession(bind=engine)
        try:
            repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx.tenant_id)
            deliveries = repo.list_deliveries(limit=1000)
            for delivery in deliveries:
                if delivery.order_id == req.order_id:
                    order_data.update(
                        {
                            "client_name": delivery.customer_name or "Cliente",
                            "address": delivery.address_street or "",
                        }
                    )
                    break
        finally:
            db.close()
    except Exception:
        # Fallback: impressão segue com dados mínimos do pedido.
        logger.warning("printer.order_lookup_failed", exc_info=True)

    job = agent.create_print_job(
        order_id=req.order_id,
        tenant_id=ctx.tenant_id,
        order_data=order_data,
        requested_by=ctx.user_id,
        is_reprint=req.is_reprint,
    )

    return {
        "success": True,
        "job": job.to_dict(),
        "escpos_preview": job.escpos_data[:200].decode("utf-8", errors="replace") if job.escpos_data else None,
    }


@router.get("/status")
async def get_printer_status(ctx: TenantContext = Depends(get_tenant_context)):
    """Get current printer status."""
    agent = get_print_agent()
    return agent.get_printer_status()


@router.get("/jobs")
async def list_print_jobs(
    limit: int = 50,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List print jobs for the current tenant."""
    agent = get_print_agent()
    jobs = agent.get_jobs_for_tenant(ctx.tenant_id, limit=limit)
    return {
        "jobs": [j.to_dict() for j in jobs],
        "count": len(jobs),
    }


@router.get("/jobs/{job_id}")
async def get_print_job(job_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    """Get a specific print job."""
    agent = get_print_agent()
    job = agent.get_job(job_id)
    if not job:
        raise HTTPException(404, "Print job not found")
    if job.tenant_id != ctx.tenant_id:
        raise HTTPException(404, "Print job not found")
    return {"job": job.to_dict()}


@router.post("/jobs/{job_id}/retry")
async def retry_print_job(job_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    """Retry a failed print job."""
    agent = get_print_agent()
    job = agent.get_job(job_id)
    if not job:
        raise HTTPException(404, "Print job not found")
    if job.tenant_id != ctx.tenant_id:
        raise HTTPException(404, "Print job not found")
    if job.status != PrintJobStatus.FAILED:
        raise HTTPException(400, "Can only retry failed jobs")

    # Create a new print job with the same data
    new_job = agent.create_print_job(
        order_id=job.order_id,
        tenant_id=job.tenant_id,
        order_data=job.order_data,
        requested_by=ctx.user_id,
        is_reprint=True,
    )

    return {
        "success": True,
        "job": new_job.to_dict(),
    }


@router.get("/orders/{order_id}/jobs")
async def get_order_print_jobs(order_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    """Get all print jobs for a specific order."""
    agent = get_print_agent()
    jobs = agent.get_jobs_for_order(order_id, ctx.tenant_id)
    return {
        "jobs": [j.to_dict() for j in jobs],
        "count": len(jobs),
    }
