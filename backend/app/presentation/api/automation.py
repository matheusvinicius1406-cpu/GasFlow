"""
Automation API — FASE 12

GET /automation/workflows — List workflows
POST /automation/workflows — Create workflow
POST /automation/workflows/{id}/execute — Execute workflow
POST /automation/runs/{id}/pause — Pause run
POST /automation/runs/{id}/cancel — Cancel run
GET /automation/approvals — List pending approvals
POST /automation/approvals/{id}/approve — Approve
POST /automation/approvals/{id}/reject — Reject
GET /automation/agents — List agents
POST /automation/agents/{id}/execute — Execute agent
GET /automation/agents/runs — List agent runs
POST /automation/kill-switch — Toggle kill switch
GET /automation/metrics — Metrics
"""

from fastapi import APIRouter, HTTPException, Depends
from app.presentation.dependencies import get_tenant_context
from app.domain.security.models import TenantContext
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from app.core.config import settings
from app.domain.automation.events import EventBus
from app.domain.automation.workflows import WorkflowDefinition
from app.domain.automation.policy import PolicyEngine, ApprovalEngine
from app.core.approval_redis import RedisApprovalEngine
from app.application.automation.workflow_engine import WorkflowEngine
from app.application.automation.agent_engine import AgentEngine
from app.application.automation.automations import (
    register_default_policies,
    create_default_agents,
    create_low_stock_workflow,
    create_receivable_overdue_workflow,
    create_customer_reactivation_workflow,
    create_order_completion_workflow,
    create_payment_confirmation_workflow,
)

router = APIRouter(prefix="/automation", tags=["automation"])

# ── Singletons ──────────────────────────────────────────

_event_bus = EventBus()
_policy_engine = PolicyEngine()
# Backend da fila de aprovações escolhido por APPROVAL_QUEUE_MODE:
# memory (default, single worker) ou redis (compartilhado entre workers —
# produção; ver rate_limit.py / REALTIME_BACKEND para o mesmo padrão).
_approval_engine = (
    RedisApprovalEngine(url=settings.approval_queue_redis_url)
    if settings.approval_queue_mode == "redis"
    else ApprovalEngine()
)
_workflow_engine = WorkflowEngine(_policy_engine, _approval_engine)
_agent_engine = AgentEngine(_policy_engine, _approval_engine, tool_registry=None)
_workflows: Dict[str, WorkflowDefinition] = {}

# Initialize defaults
register_default_policies(_policy_engine)
create_default_agents(_agent_engine)

# Register default workflows
for wf in [
    create_low_stock_workflow(),
    create_receivable_overdue_workflow(),
    create_customer_reactivation_workflow(),
    create_order_completion_workflow(),
    create_payment_confirmation_workflow(),
]:
    _workflows[wf.id] = wf


# ── Schemas ─────────────────────────────────────────────


class WorkflowCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    trigger_type: str = "MANUAL_TRIGGER"
    trigger_event: Optional[str] = None


class WorkflowExecuteRequest(BaseModel):
    context: Dict[str, Any] = {}
    correlation_id: Optional[str] = None
    dry_run: bool = False


class AgentExecuteRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=500)
    context: Dict[str, Any] = {}
    correlation_id: Optional[str] = None
    dry_run: bool = False


class ApprovalRequest(BaseModel):
    approved_by: str = Field("operator", min_length=1)
    # Se informado (e found), retoma o run pausado após aprovar.
    resume: bool = True


class KillSwitchRequest(BaseModel):
    active: bool


# ── Workflows ───────────────────────────────────────────


@router.get("/workflows")
async def list_workflows(ctx: TenantContext = Depends(get_tenant_context)):
    return {
        "workflows": [
            {"id": w.id, "name": w.name, "status": w.status.value, "steps": len(w.steps)} for w in _workflows.values()
        ]
    }


@router.post("/workflows")
async def create_workflow(req: WorkflowCreateRequest):
    wf = WorkflowDefinition(
        name=req.name, description=req.description, trigger_type=req.trigger_type, trigger_event=req.trigger_event
    )
    _workflows[wf.id] = wf
    return {"id": wf.id, "name": wf.name, "status": wf.status.value}


@router.post("/workflows/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: str, req: WorkflowExecuteRequest, ctx: TenantContext = Depends(get_tenant_context)
):
    wf = _workflows.get(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    run = _workflow_engine.execute_workflow(wf, req.context, req.correlation_id, dry_run=req.dry_run)
    return {"run_id": run.id, "status": run.status.value}


# ── Runs ────────────────────────────────────────────────


@router.get("/runs")
async def list_runs(ctx: TenantContext = Depends(get_tenant_context)):
    runs = _workflow_engine._run_history
    return {
        "runs": [
            {
                "id": r.id,
                "workflow_id": r.workflow_id,
                "status": r.status.value,
                "started_at": r.started_at.isoformat() if r.started_at else None,
            }
            for r in runs[-50:]
        ]
    }


@router.post("/runs/{run_id}/pause")
async def pause_run(run_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    if _workflow_engine.pause_run(run_id):
        return {"success": True}
    raise HTTPException(status_code=400, detail="Cannot pause run")


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    if _workflow_engine.cancel_run(run_id):
        return {"success": True}
    raise HTTPException(status_code=400, detail="Cannot cancel run")


# ── Approvals ───────────────────────────────────────────


@router.get("/approvals")
async def list_approvals(ctx: TenantContext = Depends(get_tenant_context)):
    _approval_engine.expire_old()
    return {
        "approvals": [
            {
                "id": a.id,
                "action": a.action,
                "status": a.status.value,
                "risk_level": a.risk_level,
                "created_at": a.created_at.isoformat(),
            }
            for a in _approval_engine.get_all()
        ]
    }


@router.post("/approvals/{approval_id}/approve")
async def approve_action(approval_id: str, req: ApprovalRequest, ctx: TenantContext = Depends(get_tenant_context)):
    if not _approval_engine.approve(approval_id, req.approved_by):
        raise HTTPException(status_code=400, detail="Cannot approve")
    resumed_run: Optional[str] = None
    if req.resume:
        resumed_run = _resume_paused_run(approval_id)
    return {"success": True, "resumed_run_id": resumed_run}


def _resume_paused_run(approval_id: str) -> Optional[str]:
    """Após aprovar, retoma o run pausado no step que aguardava a aprovação.

    O WorkflowEngine.valida binding (argumentos aprovados == executados) e
    executa o restante do run. Em memória por processo (histórico de runs);
    com APPROVAL_QUEUE_MODE=redis a fila em si é compartilhada entre workers.
    """
    approval = _approval_engine.get(approval_id)
    if not approval or not approval.run_id:
        return None
    run = _workflow_engine.get_run(approval.run_id)
    if not run:
        return None
    # Reconstrói a definição usada pelo run (definições vivem em _workflows).
    definition = _workflows.get(run.workflow_id)
    if not definition:
        return None
    resumed = _workflow_engine.resume_after_approval(definition, run)
    return resumed.id


@router.post("/approvals/{approval_id}/reject")
async def reject_action(approval_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    if _approval_engine.reject(approval_id):
        return {"success": True}
    raise HTTPException(status_code=400, detail="Cannot reject")


# ── Agents ──────────────────────────────────────────────


@router.get("/agents")
async def list_agents(ctx: TenantContext = Depends(get_tenant_context)):
    return {
        "agents": [
            {"id": a.id, "name": a.name, "scope": a.scope.value, "enabled": a.enabled, "risk_ceiling": a.risk_ceiling}
            for a in _agent_engine.list_agents()
        ]
    }


@router.post("/agents/{agent_id}/execute")
async def execute_agent(agent_id: str, req: AgentExecuteRequest, ctx: TenantContext = Depends(get_tenant_context)):
    run = _agent_engine.execute_agent(
        agent_id,
        req.goal,
        req.context,
        req.correlation_id,
        dry_run=req.dry_run,
    )
    return {"run_id": run.id, "status": run.status.value}


@router.get("/agents/runs")
async def list_agent_runs(ctx: TenantContext = Depends(get_tenant_context)):
    runs = _agent_engine.get_runs()
    return {
        "runs": [
            {
                "id": r.id,
                "agent_id": r.agent_id,
                "goal": r.goal,
                "status": r.status.value,
                "started_at": r.started_at.isoformat() if r.started_at else None,
            }
            for r in runs[-50:]
        ]
    }


@router.post("/agents/runs/{run_id}/stop")
async def stop_agent(run_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    if _agent_engine.stop_agent(run_id):
        return {"success": True}
    raise HTTPException(status_code=400, detail="Cannot stop agent")


# ── Kill Switch ─────────────────────────────────────────


@router.post("/kill-switch")
async def toggle_kill_switch(req: KillSwitchRequest, ctx: TenantContext = Depends(get_tenant_context)):
    if req.active:
        _policy_engine.activate_kill_switch()
    else:
        _policy_engine.deactivate_kill_switch()
    return {"active": _policy_engine.is_kill_switch_active}


@router.get("/kill-switch")
async def get_kill_switch(ctx: TenantContext = Depends(get_tenant_context)):
    return {"active": _policy_engine.is_kill_switch_active}


# ── Metrics ─────────────────────────────────────────────


@router.get("/metrics")
async def get_metrics(ctx: TenantContext = Depends(get_tenant_context)):
    return {
        "workflow": _workflow_engine.get_metrics(),
        "agent": _agent_engine.get_metrics(),
        "kill_switch": _policy_engine.is_kill_switch_active,
        "pending_approvals": len(_approval_engine.get_pending()),
    }
