"""
Printer API — F10.7

Impressão de verdade: o cupom é montado a partir do PEDIDO REAL e a fila é
persistida. Quem tem acesso USB à impressora é o app desktop (agente), que:

    1. faz poll em GET /printer/agent/next (X-GasFlow-Key)
    2. envia os bytes ESC/POS para o spooler do Windows
    3. reporta em POST /printer/agent/jobs/{id}/result
    4. publica o estado da impressora em POST /printer/agent/status

Endpoints do operador (Bearer + RBAC):
    POST /printer/print — imprime um pedido agora
    GET  /printer/status — impressora + fila (status vem do agente)
    GET  /printer/jobs — histórico da fila
    POST /printer/jobs/{job_id}/retry — reenfileira um job falhado
    GET  /printer/orders/{order_id}/jobs — jobs de um pedido

Nota de segurança: os endpoints do agente exigem a chave de serviço
(`require_whatsapp_service`, fail-closed) porque o payload contém dados do
cliente — e o backend pode estar exposto por túnel (F10).
"""

import base64
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.application.printing.print_queue import (
    PrintQueueService,
    get_agent_status,
    report_agent_status,
)
from app.application.printing.receipt_data import OrderNotFoundError
from app.domain.security.models import TenantContext
from app.infrastructure.database.dependencies import get_db
from app.presentation.dependencies import get_tenant_context, require_whatsapp_service

logger = logging.getLogger("gasflow.printer")

router = APIRouter(prefix="/printer", tags=["printer"])


class PrintRequest(BaseModel):
    order_id: str
    is_reprint: bool = False


class AgentJobResult(BaseModel):
    success: bool
    error: str = ""
    printer_name: Optional[str] = None


class AgentStatusReport(BaseModel):
    status: str  # ONLINE | OFFLINE | ERROR | PAPER_UNKNOWN | NOT_CONFIGURED
    printer_name: Optional[str] = None
    detail: str = ""


def _agent_tenant(ctx: TenantContext) -> str:
    """Tenant do agente local (app desktop) — single-tenant por instalação."""
    return ctx.tenant_id or "default"


# ── Operador ───────────────────────────────────────────────────


@router.post("/print")
def create_print_job(
    req: PrintRequest,
    db: DBSession = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Cria o job de impressão de um pedido (imediato, com o pedido real)."""
    try:
        job = PrintQueueService(db, ctx.tenant_id).enqueue(
            order_id=req.order_id,
            requested_by=ctx.user_id,
            is_reprint=req.is_reprint,
        )
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail="Pedido não encontrado") from None

    return {"success": True, "job": job.to_dict()}


@router.get("/status")
def get_printer_status(
    db: DBSession = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Estado da impressora (reportado pelo agente) + contadores da fila.

    `stale=True` significa que o último relato é velho demais (ou não existe):
    o app pode estar fechado. A tela usa isso para avisar "sem sinal" em vez de
    mostrar "Pronta" com a fila parada.
    """
    counts = PrintQueueService(db, ctx.tenant_id).queue_counts()
    agent = get_agent_status()
    return {
        "status": agent["status"],
        "printer_name": agent["printer_name"],
        "detail": agent["detail"],
        "reported_at": agent["reported_at"],
        # Nunca reportado conta como stale (não há impressora conhecida).
        "stale": bool(agent.get("stale", True)),
        "pending_jobs": counts["pending"],
        "failed_jobs": counts["failed"],
        # Vencidos (dia anterior) pedem ação do operador: reimprimir.
        "expired_jobs": counts.get("expired", 0),
        "total_jobs_today": counts["completed_today"],
    }


@router.get("/jobs")
def list_print_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    db: DBSession = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    jobs = PrintQueueService(db, ctx.tenant_id).list_jobs(limit=limit)
    return {"jobs": [j.to_dict(include_payload=True) for j in jobs], "count": len(jobs)}


@router.get("/jobs/{job_id}")
def get_print_job(
    job_id: str,
    db: DBSession = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    job = PrintQueueService(db, ctx.tenant_id).get_job(job_id)
    if not job:
        raise HTTPException(404, "Print job not found")
    return {"job": job.to_dict(include_payload=True)}


@router.post("/jobs/{job_id}/retry")
def retry_print_job(
    job_id: str,
    db: DBSession = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Reenfileira um job falhado ou reimprime um que já saiu/venceu.

    `EXPIRED` (cupom de dia anterior que não saiu sozinho) entra aqui pelo mesmo
    motivo do `COMPLETED`: o pedido do operador é explícito, então o cupom tem
    que sair AGORA — e só um job novo, com carimbo de agora, passa pelo corte do
    dia na próxima tentativa.
    """
    queue = PrintQueueService(db, ctx.tenant_id)
    job = queue.get_job(job_id)
    if not job:
        raise HTTPException(404, "Print job not found")
    if job.status in ("COMPLETED", "EXPIRED"):
        # Reimprimir um job que já saiu = novo job (com rastro de reimpressão).
        new_job = queue.enqueue(order_id=job.order_id, requested_by=ctx.user_id, is_reprint=True)
        return {"success": True, "job": new_job.to_dict()}
    job.status = "PENDING"
    job.error = None
    job.claimed_at = None
    db.commit()
    db.refresh(job)
    return {"success": True, "job": job.to_dict()}


@router.get("/orders/{order_id}/jobs")
def get_order_print_jobs(
    order_id: str,
    db: DBSession = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    jobs = PrintQueueService(db, ctx.tenant_id).jobs_for_order(order_id)
    return {"jobs": [j.to_dict() for j in jobs], "count": len(jobs)}


# ── Agente de impressão (app desktop) ──────────────────────────


@router.get("/agent/next")
def agent_claim_next(
    db: DBSession = Depends(get_db),
    ctx: TenantContext = Depends(require_whatsapp_service),
):
    """Reivindica o próximo job e devolve os bytes ESC/POS (base64).

    Fila vazia → 200 com `{"job": null, "escpos_base64": null}` (o agente
    simplesmente espera o próximo poll). Nada de 204: o agente lê o corpo para
    distinguir "sem job" de "erro", e um 204 sem corpo quebraria esse contrato.

    `expired_jobs` vai no mesmo poll de propósito: quem sabe que um cupom venceu
    é o agente (é ele que faz o claim), e assim o app consegue AVISAR o operador
    em vez de deixar o cupom vencendo em silêncio. O `claim_next` vence o que
    ficou de outro dia antes de entregar qualquer coisa.
    """
    queue = PrintQueueService(db, _agent_tenant(ctx))
    claimed = queue.claim_next()
    if claimed is None:
        return {"job": None, "escpos_base64": None, "expired_jobs": queue.expired_count()}
    job, payload = claimed
    return {
        "job": job.to_dict(),
        "escpos_base64": base64.b64encode(payload).decode("ascii"),
        "bytes": len(payload),
        "expired_jobs": queue.expired_count(),
    }


@router.post("/agent/jobs/{job_id}/result")
def agent_report_result(
    job_id: str,
    body: AgentJobResult,
    db: DBSession = Depends(get_db),
    ctx: TenantContext = Depends(require_whatsapp_service),
):
    """Resultado da impressão (COMPLETED/FAILED + motivo)."""
    job = PrintQueueService(db, _agent_tenant(ctx)).complete(
        job_id=job_id,
        success=body.success,
        error=body.error,
        printer_name=body.printer_name,
    )
    if job is None:
        raise HTTPException(404, "Print job not found")
    return {"success": True, "job": job.to_dict()}


@router.post("/agent/status")
def agent_report_status(
    body: AgentStatusReport,
    ctx: TenantContext = Depends(require_whatsapp_service),
):
    """Estado atual da impressora na máquina do operador."""
    return {"success": True, "status": report_agent_status(body.status, body.printer_name, body.detail)}
