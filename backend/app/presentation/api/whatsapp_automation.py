"""
WhatsApp Automation API — FASE 14

Endpoints for automation rules and executions.
All endpoints are tenant-scoped.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional

from app.infrastructure.database.dependencies import get_db
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository
from app.infrastructure.repositories.whatsapp_automation_repository import SQLAlchemyAutomationRepository
from app.application.whatsapp_automation.service import WhatsAppAutomationService
from app.application.whatsapp_automation.executor import ExecutionProcessor
from app.application.whatsapp_automation.whatsapp_bridge import WhatsAppSendBridge
from app.domain.whatsapp_automation.entity import AutomationRule, AutomationStatus, AutomationTriggerType
from app.presentation.dependencies import get_tenant_context
from app.domain.security.models import TenantContext

router = APIRouter(prefix="/automation/whatsapp", tags=["whatsapp-automation"])


def _get_service(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context)) -> WhatsAppAutomationService:
    auto_repo = SQLAlchemyAutomationRepository(db, ctx.tenant_id)
    client_repo = SQLAlchemyClientRepository(db, ctx.tenant_id)
    order_repo = SQLAlchemyOrderRepository(db, ctx.tenant_id)
    return WhatsAppAutomationService(auto_repo, client_repo, order_repo)


def _get_processor(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context)) -> ExecutionProcessor:
    auto_repo = SQLAlchemyAutomationRepository(db, ctx.tenant_id)
    return ExecutionProcessor(auto_repo)


# ── Schemas ──────────────────────────────────────────

class RuleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    trigger_type: str = "MANUAL"
    segment_id: Optional[int] = None
    min_score: Optional[float] = None
    confidence_filter: Optional[str] = None
    message_template: str = Field("", max_length=4096)
    account_id: str = "primary"
    max_messages_per_day: int = 1
    cooldown_days: int = 7
    requires_approval: bool = True


class RuleUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    message_template: Optional[str] = None
    min_score: Optional[float] = None
    confidence_filter: Optional[str] = None
    cooldown_days: Optional[int] = None
    max_messages_per_day: Optional[int] = None
    requires_approval: Optional[bool] = None


class PreviewRequest(BaseModel):
    template: str
    customer_codigo: str


# ── Rules ────────────────────────────────────────────

@router.get("/rules")
def list_rules(
    status: Optional[str] = Query(None),
    service: WhatsAppAutomationService = Depends(_get_service),
):
    rules = service.list_rules(status=status)
    return {"rules": [r.to_dict() for r in rules], "total": len(rules)}


@router.post("/rules")
def create_rule(
    req: RuleCreateRequest,
    service: WhatsAppAutomationService = Depends(_get_service),
):
    rule = AutomationRule(
        name=req.name,
        description=req.description,
        trigger_type=AutomationTriggerType(req.trigger_type),
        status=AutomationStatus.DRAFT,
        segment_id=req.segment_id,
        min_score=req.min_score,
        confidence_filter=req.confidence_filter,
        message_template=req.message_template,
        account_id=req.account_id,
        max_messages_per_day=req.max_messages_per_day,
        cooldown_days=req.cooldown_days,
        requires_approval=req.requires_approval,
    )
    created = service.create_rule(rule)
    return created.to_dict()


@router.get("/rules/{rule_id}")
def get_rule(
    rule_id: int,
    service: WhatsAppAutomationService = Depends(_get_service),
):
    rule = service.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule.to_dict()


@router.put("/rules/{rule_id}")
def update_rule(
    rule_id: int,
    req: RuleUpdateRequest,
    service: WhatsAppAutomationService = Depends(_get_service),
):
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None}
    rule = service.update_rule(rule_id, **kwargs)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule.to_dict()


@router.delete("/rules/{rule_id}")
def delete_rule(
    rule_id: int,
    service: WhatsAppAutomationService = Depends(_get_service),
):
    if not service.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"success": True}


@router.post("/rules/{rule_id}/activate")
def activate_rule(
    rule_id: int,
    service: WhatsAppAutomationService = Depends(_get_service),
):
    rule = service.activate_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule.to_dict()


@router.post("/rules/{rule_id}/pause")
def pause_rule(
    rule_id: int,
    service: WhatsAppAutomationService = Depends(_get_service),
):
    rule = service.pause_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule.to_dict()


# ── Execution ────────────────────────────────────────

@router.post("/rules/{rule_id}/execute")
def execute_rule(
    rule_id: int,
    service: WhatsAppAutomationService = Depends(_get_service),
):
    result = service.execute_rule(rule_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/executions")
def list_executions(
    rule_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    service: WhatsAppAutomationService = Depends(_get_service),
):
    execs = service.list_executions(rule_id=rule_id, status=status, limit=limit)
    return {"executions": [e.to_dict() for e in execs], "total": len(execs)}


@router.post("/executions/{execution_id}/approve")
def approve_execution(
    execution_id: int,
    service: WhatsAppAutomationService = Depends(_get_service),
):
    execution = service.approve_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution.to_dict()


@router.post("/executions/{execution_id}/cancel")
def cancel_execution(
    execution_id: int,
    service: WhatsAppAutomationService = Depends(_get_service),
):
    execution = service.cancel_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution.to_dict()


# ── Preview & Metrics ────────────────────────────────

@router.post("/preview")
def preview_template(
    req: PreviewRequest,
    service: WhatsAppAutomationService = Depends(_get_service),
):
    result = service.preview_template(req.template, req.customer_codigo)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/metrics")
def get_metrics(
    service: WhatsAppAutomationService = Depends(_get_service),
):
    return service.get_metrics()


# ── Execution Processing (FASE 14.5) ─────────────────

@router.post("/executions/{execution_id}/process")
async def process_execution(
    execution_id: int,
    processor: ExecutionProcessor = Depends(_get_processor),
):
    """Process a single execution: send via WhatsApp bridge."""
    result = await processor.process_execution(execution_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/process-pending")
async def process_pending(
    limit: int = Query(10, ge=1, le=50),
    processor: ExecutionProcessor = Depends(_get_processor),
):
    """Process all pending executions."""
    result = await processor.process_pending_executions(limit=limit)
    return result


@router.get("/audit")
async def get_audit_log(
    limit: int = Query(100, ge=1, le=500),
    processor: ExecutionProcessor = Depends(_get_processor),
):
    """Get automation audit log."""
    return {"entries": processor.get_audit_log(limit=limit)}


@router.get("/connection-check")
async def check_connection(
    account_id: str = Query("primary"),
):
    """Check if WhatsApp service is connected."""
    bridge = WhatsAppSendBridge()
    result = await bridge.check_connection(account_id=account_id)
    return result
