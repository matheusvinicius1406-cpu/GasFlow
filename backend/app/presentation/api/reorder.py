"""
Reorder Intelligence API — FASE 13.2

Endpoints for reorder prediction and analysis.
All endpoints are tenant-scoped.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.infrastructure.database.dependencies import get_db
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository
from app.application.reorder.service import ReorderService
from app.presentation.dependencies import get_tenant_context
from app.domain.security.models import TenantContext

router = APIRouter(prefix="/reorder", tags=["Reorder Intelligence"])


def _get_service(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context)) -> ReorderService:
    client_repo = SQLAlchemyClientRepository(db, ctx.tenant_id)
    order_repo = SQLAlchemyOrderRepository(db, ctx.tenant_id)
    return ReorderService(client_repo, order_repo)


@router.get("/opportunities")
def list_opportunities(
    status: str = Query(None, description="Filter by status: READY, DUE, OVERDUE, DORMANT"),
    confidence: str = Query(None, description="Filter by confidence: HIGH, MEDIUM, LOW"),
    min_score: float = Query(None, description="Minimum reorder score (0-100)"),
    service: ReorderService = Depends(_get_service),
):
    """List all reorder opportunities with optional filters."""
    opps = service.get_opportunities(status=status, confidence=confidence, min_score=min_score)
    return {"opportunities": [o.to_dict() for o in opps], "total": len(opps)}


@router.get("/customers/{customer_codigo}")
def get_customer_reorder(
    customer_codigo: str,
    service: ReorderService = Depends(_get_service),
):
    """Get reorder analysis for a specific customer."""
    opp = service.analyze_customer(customer_codigo)
    if not opp:
        raise HTTPException(status_code=404, detail="Customer not found or has no orders")
    return opp.to_dict()


@router.get("/summary")
def get_summary(
    status: str = Query(None),
    confidence: str = Query(None),
    service: ReorderService = Depends(_get_service),
):
    """Get aggregate summary of reorder opportunities."""
    summary = service.get_summary(status=status, confidence=confidence)
    return summary.to_dict()
