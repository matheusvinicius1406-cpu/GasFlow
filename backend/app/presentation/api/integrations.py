"""
Integrations API — conexão de sites de revendas ao GasFlow (agente de ancoragem).

Auth:
  - Endpoints de gestão: require_permission("integration.read"/"integration.write")
  - POST /integrations/import: token POR integração (header X-Integration-Token)
    — é o canal público do agente da revenda.
  - POST /integrations/{id}/sync-run: service key OU usuário autenticado com
    integration.write (canal confiável agente→backend).

O agente roda na infraestrutura do próprio dono do site (ou com autorização
dele); nenhuma técnica de evasão é usada — HTTP puro com credenciais
configuradas.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.application.integrations.import_service import (
    IntegrationError,
    IntegrationImportService,
)
from app.infrastructure.database.dependencies import get_db
from app.infrastructure.repositories.integration_model import IntegrationModel
from app.domain.security.models import TenantContext
from app.presentation.dependencies import get_tenant_context, require_permission

logger = logging.getLogger("gasflow")

router = APIRouter(prefix="/integrations", tags=["Integrations"])


# ── Schemas ──────────────────────────────────────────────


class IntegrationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=255)
    base_url: str = Field(min_length=8, max_length=500)
    orders_path: Optional[str] = Field(default=None, max_length=200)
    auth_type: str = Field(default="none", pattern="^(none|basic|token|cookie)$")
    auth_config: Optional[Dict[str, str]] = None
    field_mapping: Optional[Dict[str, str]] = None
    selectors: Optional[Dict[str, str]] = None
    sync_interval_minutes: int = Field(default=5, ge=1, le=1440)


class IntegrationUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=255)
    base_url: Optional[str] = Field(default=None, max_length=500)
    orders_path: Optional[str] = Field(default=None, max_length=200)
    auth_type: Optional[str] = Field(default=None, pattern="^(none|basic|token|cookie)$")
    auth_config: Optional[Dict[str, str]] = None
    field_mapping: Optional[Dict[str, str]] = None
    selectors: Optional[Dict[str, str]] = None
    sync_interval_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    is_active: Optional[bool] = None


class ImportOrderRequest(BaseModel):
    integration_id: str
    order: Dict[str, Any]


class SyncRunRequest(BaseModel):
    orders: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    trigger: str = Field(default="agent", pattern="^(manual|scheduler|agent)$")


# ── Helpers ──────────────────────────────────────────────


def _svc(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context)):
    return IntegrationImportService(db=db, tenant_id=ctx.tenant_id)


def _to_dict(model: IntegrationModel) -> Dict[str, Any]:
    """Serializa integração; auth_config NUNCA sai daqui (redacted)."""
    return {
        "id": model.id,
        "name": model.name,
        "description": model.description,
        "base_url": model.base_url,
        "orders_path": model.orders_path,
        "auth_type": model.auth_type,
        "has_credentials": bool(model.auth_config),
        "import_token": model.import_token,
        "field_mapping": model.field_mapping,
        "selectors": model.selectors,
        "sync_interval_minutes": model.sync_interval_minutes,
        "is_active": model.is_active,
        "last_sync_at": model.last_sync_at.isoformat() if model.last_sync_at else None,
        "last_sync_status": model.last_sync_status,
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }


def _or_404(service: IntegrationImportService, integration_id: str) -> IntegrationModel:
    integration = service.get_integration(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integração não encontrada.")
    return integration


def _err(e: IntegrationError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.message)


# ── CRUD ─────────────────────────────────────────────────


@router.get("")
def list_integrations(
    include_inactive: bool = Query(default=True),
    svc: IntegrationImportService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("integration.read")),
):
    rows = svc.list_integrations(include_inactive=include_inactive)
    return {"integrations": [_to_dict(r) for r in rows], "total": len(rows)}


@router.post("", status_code=201)
def create_integration(
    body: IntegrationCreateRequest,
    svc: IntegrationImportService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("integration.write")),
):
    model = IntegrationModel(
        id=str(uuid.uuid4()),
        tenant_id=svc.tenant_id,
        name=body.name.strip(),
        description=body.description,
        base_url=body.base_url.strip(),
        orders_path=body.orders_path,
        auth_type=body.auth_type,
        auth_config=body.auth_config or None,
        import_token=IntegrationModel.generate_import_token(),
        field_mapping=body.field_mapping or None,
        selectors=body.selectors or None,
        sync_interval_minutes=body.sync_interval_minutes,
    )
    svc.db.add(model)
    svc.db.commit()
    svc.db.refresh(model)
    logger.info("integration created", extra={"integration_id": model.id})
    return _to_dict(model)


@router.get("/{integration_id}")
def get_integration(
    integration_id: str,
    svc: IntegrationImportService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("integration.read")),
):
    return _to_dict(_or_404(svc, integration_id))


@router.put("/{integration_id}")
def update_integration(
    integration_id: str,
    body: IntegrationUpdateRequest,
    svc: IntegrationImportService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("integration.write")),
):
    model = _or_404(svc, integration_id)
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(model, key, value)
    svc.db.commit()
    svc.db.refresh(model)
    return _to_dict(model)


@router.delete("/{integration_id}")
def delete_integration(
    integration_id: str,
    svc: IntegrationImportService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("integration.write")),
):
    """Soft delete — desativa a integração (histórico de sync é preservado)."""
    model = _or_404(svc, integration_id)
    model.is_active = False
    svc.db.commit()
    return {"ok": True, "id": model.id, "is_active": model.is_active}


@router.post("/{integration_id}/rotate-token")
def rotate_token(
    integration_id: str,
    svc: IntegrationImportService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("integration.write")),
):
    model = _or_404(svc, integration_id)
    model.import_token = IntegrationModel.generate_import_token()
    svc.db.commit()
    return {"ok": True, "import_token": model.import_token}


# ── Teste de conexão / Sync ──────────────────────────────


@router.post("/{integration_id}/test-connection")
async def test_connection(
    integration_id: str,
    svc: IntegrationImportService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("integration.write")),
):
    """Dry-run: acessa o site e devolve cabeçalhos candidatos a tabela de pedidos."""
    model = _or_404(svc, integration_id)
    try:
        return await svc.test_connection(model)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha no teste: {e}") from e


@router.post("/{integration_id}/sync")
def sync_manual(
    integration_id: str,
    svc: IntegrationImportService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("integration.write")),
):
    """Dispara sincronização manual. O scraping roda no AGENTE — isso enfileira
    a execução consultando o agente via /agent/dispatch (pull model). Sem agente
    rodando, use o botão 'Testar conexão' para validar o site.

    Implementação prática: marca last_sync_status='pending-agent' e registra um
    SyncLog de trigger='manual' — o agente pega na próxima rodada de poll.
    """
    model = _or_404(svc, integration_id)
    if not model.is_active:
        raise HTTPException(status_code=409, detail="Integração inativa.")
    return {
        "ok": True,
        "integration_id": model.id,
        "message": "Execução delegada ao agente (pull model). O agente sincroniza na próxima rodada.",
    }


@router.post("/sync-all")
def sync_all(
    svc: IntegrationImportService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("integration.write")),
):
    """Marca todas as integrações ativas para sincronização pelo agente.

    Pensado para cron externo: `curl -X POST .../integrations/sync-all`.
    O agente (pull model) busca e processa; o backend nunca faz scraping
    pesado dentro do processo FastAPI.
    """
    rows = [r for r in svc.list_integrations(include_inactive=False)]
    return {
        "ok": True,
        "queued": len(rows),
        "integration_ids": [r.id for r in rows],
        "message": "Agente processará na próxima rodada de poll.",
    }


@router.post("/{integration_id}/sync-run", status_code=201)
def sync_run(
    integration_id: str,
    body: SyncRunRequest,
    svc: IntegrationImportService = Depends(_svc),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Agente entrega o lote extraído: pedidos + erros do scraping.

    Permissão: usuário autenticado com integration.write (o agente autentica
    com credenciais de usuário de serviço ou envia via /import com token).
    """
    if not ctx.has_permission("integration.write"):
        raise HTTPException(status_code=403, detail="Permissão necessária: integration.write")
    model = _or_404(svc, integration_id)
    try:
        log = svc.process_sync_run(
            model,
            orders=body.orders,
            agent_errors=body.errors,
            trigger=body.trigger,
        )
    except IntegrationError as e:
        raise _err(e) from e
    return {
        "sync_log_id": log.id,
        "status": log.status,
        "total_found": log.total_found,
        "total_imported": log.total_imported,
        "total_errors": log.total_errors,
        "error_details": log.error_details,
    }


# ── Import (webhook público do agente, token por integração) ────


@router.post("/import", status_code=201)
def import_order(
    body: ImportOrderRequest,
    x_integration_token: str = Header(..., alias="X-Integration-Token"),
    db: Session = Depends(get_db),
):
    """Recebe UM pedido do agente. Auth = token da integração (header).

    Público de propósito: o agente da revenda não tem conta no GasFlow —
    o par (integration_id, import_token) é a credencial.
    """
    model = (
        db.query(IntegrationModel)
        .filter(
            IntegrationModel.id == body.integration_id,
            IntegrationModel.import_token == x_integration_token,
        )
        .first()
    )
    if not model:
        raise HTTPException(status_code=401, detail="Token de integração inválido.")
    svc = IntegrationImportService(db=db, tenant_id=model.tenant_id)
    result = svc.process_order(model, body.order)
    return {
        "imported_order_id": result.imported_order_id,
        "status": result.status,
        "gasflow_order_codigo": result.gasflow_order_codigo,
        "error_message": result.error_message,
    }


# ── Consultas ────────────────────────────────────────────


@router.get("/{integration_id}/logs")
def list_logs(
    integration_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    svc: IntegrationImportService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("integration.read")),
):
    _or_404(svc, integration_id)
    logs = svc.list_sync_logs(integration_id, limit=limit)
    return {
        "logs": [
            {
                "id": log_row.id,
                "started_at": log_row.started_at.isoformat() if log_row.started_at else None,
                "finished_at": log_row.finished_at.isoformat() if log_row.finished_at else None,
                "status": log_row.status,
                "trigger": log_row.trigger,
                "total_found": log_row.total_found,
                "total_imported": log_row.total_imported,
                "total_errors": log_row.total_errors,
                "error_details": log_row.error_details,
            }
            for log_row in logs
        ]
    }


@router.get("/{integration_id}/orders")
def list_imported(
    integration_id: str,
    status: Optional[str] = Query(default=None, pattern="^(pending|success|error)$"),
    limit: int = Query(default=200, ge=1, le=500),
    svc: IntegrationImportService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("integration.read")),
):
    _or_404(svc, integration_id)
    rows = svc.list_imported_orders(integration_id, status=status, limit=limit)
    return {
        "orders": [
            {
                "id": r.id,
                "external_id": r.external_id,
                "status": r.status,
                "error_message": r.error_message,
                "gasflow_order_codigo": r.gasflow_order_codigo,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "processed_at": r.processed_at.isoformat() if r.processed_at else None,
            }
            for r in rows
        ]
    }


@router.get("/{integration_id}/orders/{imported_order_id}")
def get_imported(
    integration_id: str,
    imported_order_id: str,
    svc: IntegrationImportService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("integration.read")),
):
    row = svc.get_imported_order(imported_order_id)
    if not row or row.integration_id != integration_id:
        raise HTTPException(status_code=404, detail="Pedido importado não encontrado.")
    return {
        "id": row.id,
        "external_id": row.external_id,
        "external_data": row.external_data,
        "status": row.status,
        "error_message": row.error_message,
        "gasflow_order_codigo": row.gasflow_order_codigo,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
    }


@router.post("/{integration_id}/orders/{imported_order_id}/reprocess")
def reprocess_imported(
    integration_id: str,
    imported_order_id: str,
    svc: IntegrationImportService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("integration.write")),
):
    """Reimporta um pedido com erro (ex.: estoque reposto no backend)."""
    _or_404(svc, integration_id)
    try:
        result = svc.reprocess(imported_order_id)
    except IntegrationError as e:
        raise _err(e) from e
    return {
        "imported_order_id": result.imported_order_id,
        "status": result.status,
        "gasflow_order_codigo": result.gasflow_order_codigo,
        "error_message": result.error_message,
    }
