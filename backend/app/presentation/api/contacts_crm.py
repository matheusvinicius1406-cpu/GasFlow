"""
Contacts CRM API — sincronização WhatsApp ↔ clientes, VCF e enriquecimento.

Endpoints (sob /clients/contacts — o CRUD completo de clientes continua em
/clients, isto é a superfície específica de contatos/WhatsApp):
    POST /clients/contacts/sync-batch   — lote do serviço WhatsApp (upsert por telefone)
    POST /clients/contacts/import-vcf   — importar arquivo .vcf (parser próprio, sem dep nova)
    GET  /clients/contacts/export-vcf   — exportar clientes como .vcf
    POST /clients/contacts/{codigo}/enrich — enriquecimento de endereço via LLM

Autenticação: get_tenant_context (usuário do CRM).
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional

from sqlalchemy.orm import Session

from app.application.contacts.service import ContactService
from app.domain.security.models import TenantContext
from app.infrastructure.database.dependencies import get_db
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.presentation.dependencies import (
    get_tenant_context,
    require_permission,
    require_whatsapp_service,
)

router = APIRouter(prefix="/clients/contacts", tags=["contacts-crm"])


class ContactSyncItem(BaseModel):
    telefone: str
    nome: Optional[str] = None
    is_whatsapp: bool = True
    marketing_status: Optional[str] = None
    last_interaction_at: Optional[str] = None


class SyncBatchRequest(BaseModel):
    contacts: List[ContactSyncItem]


class ReactivateRequest(BaseModel):
    days: Optional[int] = None
    limit: int = 100
    dry_run: bool = False


def _repo(db: Session, ctx: TenantContext) -> SQLAlchemyClientRepository:
    return SQLAlchemyClientRepository(db, ctx.tenant_id)


def _svc(db: Session, ctx: TenantContext) -> ContactService:
    return ContactService(_repo(db, ctx))


@router.post("/sync-batch")
def sync_batch(
    payload: SyncBatchRequest,
    db: Session = Depends(get_db),
    # Somente o serviço WhatsApp (crm-sync.ts, X-GasFlow-Key) grava contatos
    # em lote. Sem fallback JWT: um token de usuário vazado não pode
    # sobrescrever o CRM em massa (fail-closed se a chave não estiver
    # configurada no backend).
    ctx: TenantContext = Depends(require_whatsapp_service),
):
    """Upsert em lote de contatos vindos do serviço WhatsApp (ou manual)."""
    svc = _svc(db, ctx)
    results = svc.sync_batch([item.model_dump() for item in payload.contacts])
    created = sum(1 for r in results if r.get("action") == "created")
    updated = sum(1 for r in results if r.get("action") == "updated")
    errors = sum(1 for r in results if r.get("action") == "error")
    return {"total": len(results), "created": created, "updated": updated, "errors": errors, "results": results}


@router.post("/import-vcf")
async def import_vcf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("customer.create")),
):
    """Importa contatos de um arquivo .vcf (upsert por telefone).

    Parser vCard mínimo embutido (FN + TEL) — sem dependência externa:
    o formato é textual e os campos relevantes são simples.
    """
    raw = (await file.read()).decode("utf-8", errors="replace")
    contacts = _parse_vcf(raw)
    if not contacts:
        raise HTTPException(status_code=400, detail="Nenhum contato com telefone encontrado no .vcf.")
    svc = _svc(db, ctx)
    results = svc.sync_batch(contacts)
    created = sum(1 for r in results if r.get("action") == "created")
    updated = sum(1 for r in results if r.get("action") in ("updated", "unchanged"))
    return {"imported": len(results), "created": created, "updated": updated, "results": results}


def _parse_vcf(raw: str) -> List[dict]:
    """Extrai (nome, telefone) de um vCard 3.0/4.0 simples.

    Suporta múltiplos TELs por card (todos viram contatos com o mesmo nome).
    """
    contacts: List[dict] = []
    fn: Optional[str] = None
    tels: List[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("BEGIN:VCARD"):
            fn, tels = None, []
        elif line.upper().startswith("FN"):
            fn = line.split(":", 1)[1].strip() or None
        elif line.upper().startswith("TEL"):
            tel = line.split(":", 1)[1].strip()
            if tel:
                tels.append(tel)
        elif line.upper().startswith("END:VCARD"):
            for tel in tels:
                contacts.append({"telefone": tel, "nome": fn, "is_whatsapp": None})
            fn, tels = None, []
    return contacts


@router.get("/export-vcf")
def export_vcf(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Exporta os clientes do tenant como arquivo .vcf."""
    repo = _repo(db, ctx)
    clients = repo.listar_todos()

    lines: List[str] = []
    for c in clients:
        display = c.nome or f"Contato {c.telefone}"
        lines.append("BEGIN:VCARD")
        lines.append("VERSION:3.0")
        lines.append(f"FN:{_vcf_escape(display)}")
        lines.append(f"N:{_vcf_escape(display)};;;;")
        lines.append(f"TEL;TYPE=CELL:+{c.telefone}")
        if c.rua and c.rua != "A definir":
            adr = ";".join(["", "", _vcf_escape(c.rua or ""), _vcf_escape(c.complemento or ""), "", "", ""])
            lines.append(f"ADR;TYPE=HOME:{adr}")
        lines.append("END:VCARD")

    from fastapi.responses import Response

    content = "\r\n".join(lines) + "\r\n"
    return Response(
        content=content,
        media_type="text/vcard",
        headers={"Content-Disposition": "attachment; filename=gasflow-contatos.vcf"},
    )


def _vcf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\,").replace("\n", "\\n")


@router.post("/reactivate")
def reactivate_inactive(
    payload: ReactivateRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("customer.update")),
):
    """Cria executions de reativação para clientes inativos (opt-in only).

    As mensagens são enviadas pelo executor de automações existente
    (POST /whatsapp-automation/process-pending) — com retry, idempotência
    e anti-ban. dry_run=true apenas lista os candidatos.
    """
    from app.application.contacts.reactivate import ReactivationService

    service = ReactivationService(db, _repo(db, ctx))
    if payload.dry_run:
        return service.preview(days=payload.days, limit=payload.limit)
    return service.run(days=payload.days, limit=payload.limit)


@router.post("/{codigo}/enrich")
def enrich_contact(
    codigo: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("customer.update")),
):
    """Enriquecimento IA: extrai endereço embutido no nome do contato."""
    svc = _svc(db, ctx)
    result = svc.enrich_with_ai(codigo)
    if not result.get("success") and result.get("error") == "Cliente não encontrado":
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    return result


@router.get("")
def list_contacts(
    search: Optional[str] = None,
    status: Optional[str] = None,
    missing_address: bool = False,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Lista contatos do CRM com filtros de WhatsApp (usa o buscar() existente)."""
    repo = _repo(db, ctx)
    clients, total = repo.buscar(query=search or "", page=page, page_size=min(page_size, 200))
    items = []
    for c in clients:
        if status and c.marketing_status != status:
            continue
        if missing_address and c.rua not in ("A definir",):
            continue
        items.append(
            {
                "codigo": c.codigo,
                "nome": c.nome,
                "telefone": c.telefone,
                "has_name": c.has_name,
                "is_whatsapp": c.is_whatsapp,
                "marketing_status": c.marketing_status,
                "endereco_definido": bool(c.rua and c.rua != "A definir"),
                "last_interaction_at": c.last_interaction_at.isoformat() if c.last_interaction_at else None,
                "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
            }
        )
    return {"total": total, "page": page, "page_size": page_size, "contacts": items}
