"""
Segmentation API — FASE 13.1

CRM customer segmentation endpoints.
Deterministic, auditable, tenant-scoped.

Endpoints:
- GET /segments — List all segments
- POST /segments — Create segment
- GET /segments/:id — Get segment detail
- PUT /segments/:id — Update segment
- DELETE /segments/:id — Delete segment
- POST /segments/:id/evaluate — Evaluate segment (count members)
- POST /segments/:id/preview — Preview segment members
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from app.presentation.dependencies import get_tenant_context
from app.domain.security.models import TenantContext
from pydantic import BaseModel, Field
from typing import Optional, List, Any

from sqlalchemy.orm import Session
from app.infrastructure.database.dependencies import get_db
from app.infrastructure.repositories.segmentation_repository import SQLAlchemySegmentRepository
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository
from app.infrastructure.repositories.financial_repositories import SQLAlchemyReceivableRepository
from app.application.segmentation.service import SegmentService
from app.domain.segmentation.entity import Segment, SegmentRule, RuleField, RuleOperator, SegmentStatus

router = APIRouter(prefix="/segments", tags=["segmentation"])


# ── Schemas ──────────────────────────────────────────────


class RuleSchema(BaseModel):
    field: str
    operator: str
    value: Any = None


class SegmentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=1000)
    rules: List[RuleSchema] = []
    rule_logic: str = Field("AND", pattern="^(AND|OR)$")


class SegmentUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    rules: Optional[List[RuleSchema]] = None
    rule_logic: Optional[str] = Field(None, pattern="^(AND|OR)$")
    status: Optional[str] = None


class SegmentResponse(BaseModel):
    id: int
    name: str
    description: str
    rules: List[dict]
    rule_logic: str
    status: str
    member_count: int
    last_evaluated_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SegmentPreviewResponse(BaseModel):
    total_evaluated: int
    total_matches: int
    members: List[dict]


class AvailableRulesResponse(BaseModel):
    fields: List[dict]
    operators: List[dict]


# ── Endpoints ────────────────────────────────────────────


@router.get("", response_model=List[SegmentResponse])
async def list_segments(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List all segments."""
    repo = SQLAlchemySegmentRepository(db, ctx.tenant_id)
    segments = repo.list_all(status=status)
    return [SegmentResponse(**s.to_dict()) for s in segments]


@router.post("", response_model=SegmentResponse, status_code=201)
async def create_segment(
    req: SegmentCreateRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Create a new segment."""
    repo = SQLAlchemySegmentRepository(db, ctx.tenant_id)

    # Validate rules
    rules = []
    for r in req.rules:
        try:
            rule = SegmentRule(
                field=RuleField(r.field),
                operator=RuleOperator(r.operator),
                value=r.value,
            )
            rules.append(rule)
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=400, detail=f"Invalid rule: {e}")

    segment = Segment(
        name=req.name,
        description=req.description,
        rules=rules,
        rule_logic=req.rule_logic,
        status=SegmentStatus.DRAFT,
    )

    created = repo.create(segment)
    return SegmentResponse(**created.to_dict())


@router.get("/rules", response_model=AvailableRulesResponse)
async def get_available_rules():
    """Get available rule fields and operators."""
    fields = [
        {
            "value": f.value,
            "label": f.value.replace("_", " ").title(),
            "type": "number"
            if f
            in (
                RuleField.TOTAL_ORDERS,
                RuleField.TOTAL_SPENT,
                RuleField.AVERAGE_TICKET,
                RuleField.DAYS_SINCE_LAST_ORDER,
                RuleField.ORDER_FREQUENCY,
            )
            else "string"
            if f in (RuleField.CLIENT_TYPE, RuleField.FAVORITE_PRODUCT, RuleField.PAYMENT_STATUS)
            else "boolean",
        }
        for f in RuleField
    ]
    operators = [{"value": o.value, "label": o.value.replace("_", " ").title()} for o in RuleOperator]
    return AvailableRulesResponse(fields=fields, operators=operators)


@router.get("/{segment_id}", response_model=SegmentResponse)
async def get_segment(
    segment_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get segment detail."""
    repo = SQLAlchemySegmentRepository(db, ctx.tenant_id)
    segment = repo.find_by_id(segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")
    return SegmentResponse(**segment.to_dict())


@router.put("/{segment_id}", response_model=SegmentResponse)
async def update_segment(
    segment_id: int,
    req: SegmentUpdateRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Update a segment."""
    repo = SQLAlchemySegmentRepository(db, ctx.tenant_id)
    segment = repo.find_by_id(segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    if req.name is not None:
        segment.name = req.name
    if req.description is not None:
        segment.description = req.description
    if req.rule_logic is not None:
        segment.rule_logic = req.rule_logic
    if req.status is not None:
        segment.status = SegmentStatus(req.status)

    if req.rules is not None:
        rules = []
        for r in req.rules:
            try:
                rule = SegmentRule(
                    field=RuleField(r.field),
                    operator=RuleOperator(r.operator),
                    value=r.value,
                )
                rules.append(rule)
            except (ValueError, KeyError) as e:
                raise HTTPException(status_code=400, detail=f"Invalid rule: {e}")
        segment.rules = rules

    updated = repo.update(segment)
    return SegmentResponse(**updated.to_dict())


@router.delete("/{segment_id}")
async def delete_segment(
    segment_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Delete a segment."""
    repo = SQLAlchemySegmentRepository(db, ctx.tenant_id)
    if not repo.delete(segment_id):
        raise HTTPException(status_code=404, detail="Segment not found")
    return {"success": True}


@router.post("/{segment_id}/evaluate")
async def evaluate_segment(
    segment_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Evaluate segment and update member count."""
    repo = SQLAlchemySegmentRepository(db, ctx.tenant_id)
    segment = repo.find_by_id(segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    # Get all customer codes for this tenant
    client_repo = SQLAlchemyClientRepository(db, ctx.tenant_id)
    clients, _ = client_repo.buscar(query="", page=1, page_size=10000)
    all_codes = [c.codigo for c in clients]

    # Evaluate
    service = SegmentService(
        order_repository=SQLAlchemyOrderRepository(db, ctx.tenant_id),
        client_repository=client_repo,
        receivable_repository=SQLAlchemyReceivableRepository(db, ctx.tenant_id),
    )

    count = service.count_segment_members(segment, all_codes)
    repo.update_member_count(segment_id, count)

    return {
        "segment_id": segment_id,
        "member_count": count,
        "total_evaluated": len(all_codes),
        "last_evaluated_at": segment.last_evaluated_at.isoformat() if segment.last_evaluated_at else None,
    }


@router.post("/{segment_id}/preview", response_model=SegmentPreviewResponse)
async def preview_segment(
    segment_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Preview segment members without persisting."""
    repo = SQLAlchemySegmentRepository(db, ctx.tenant_id)
    segment = repo.find_by_id(segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    # Get all customer codes
    client_repo = SQLAlchemyClientRepository(db, ctx.tenant_id)
    clients, _ = client_repo.buscar(query="", page=1, page_size=10000)
    all_codes = [c.codigo for c in clients]

    # Preview
    service = SegmentService(
        order_repository=SQLAlchemyOrderRepository(db, ctx.tenant_id),
        client_repository=client_repo,
        receivable_repository=SQLAlchemyReceivableRepository(db, ctx.tenant_id),
    )

    result = service.preview_segment(segment, all_codes)
    result["members"] = result["members"][:limit]

    return SegmentPreviewResponse(**result)
