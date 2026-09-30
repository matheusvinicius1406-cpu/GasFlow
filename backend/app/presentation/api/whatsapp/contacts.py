"""
Contacts CRM API — sincronização WhatsApp ↔ clientes, VCF e enriquecimento.

Endpoints (sob /whatsapp/contacts — reorg F5; o CRUD completo de clientes
continua em /clients, isto é a superfície específica de contatos/WhatsApp):
    POST /whatsapp/contacts/sync-batch     — lote do serviço WhatsApp (upsert por telefone)
    POST /whatsapp/contacts/sync           — dispara coleta no serviço WhatsApp (proxy)
    POST /whatsapp/contacts/import-vcf     — importar arquivo .vcf (parser próprio, sem dep nova)
    GET  /whatsapp/contacts/export-vcf     — exportar clientes como .vcf
    POST /whatsapp/contacts/reactivate     — reativação de inativos (opt-in only)
    POST /whatsapp/contacts/{codigo}/enrich — enriquecimento de endereço via LLM
    GET  /whatsapp/contacts                — listagem com filtros de WhatsApp

Autenticação: get_tenant_context (usuário do CRM).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.application.contacts.service import ContactService
from app.application.contacts.vcf import parse_vcf
from app.domain.security.models import TenantContext
from app.infrastructure.database.dependencies import get_db
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.presentation.dependencies import (
    get_tenant_context,
    require_permission,
    require_renamer_enabled,
    require_whatsapp_service,
)

router = APIRouter(prefix="/whatsapp/contacts", tags=["contacts-crm"])


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


def _parse_last_interaction(value: object) -> Optional[datetime]:
    """ISO string → datetime (naive, UTC). Malformed/None → None (sem no-op).

    O SQLAlchemy (SQLite) só aceita datetime/date — uma string ISO passaria
    direto e derrubaria o INSERT com TypeError, descartando o contato do
    lote em silêncio. Valor inválido é descartado (contato ainda sincroniza).
    """
    if not value or isinstance(value, datetime):
        return value if isinstance(value, datetime) else None  # type: ignore[return-value]
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _repo(db: Session, ctx: TenantContext) -> SQLAlchemyClientRepository:
    return SQLAlchemyClientRepository(db, ctx.tenant_id)


def _svc(db: Session, ctx: TenantContext) -> ContactService:
    return ContactService(_repo(db, ctx))


@router.post("/sync")
async def sync_contacts():
    """Dispara a coleta de contatos no serviço WhatsApp (proxy legado).

    Reorg F5: antes era POST /whatsapp/contacts/sync no router de contas;
    agora vive no namespace unificado de contatos.
    """
    from app.presentation.api.whatsapp.accounts import _proxy_post

    return await _proxy_post("/contacts/sync")


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
    items = []
    for item in payload.contacts:
        data = item.model_dump()
        data["last_interaction_at"] = _parse_last_interaction(data.get("last_interaction_at"))
        items.append(data)
    results = svc.sync_batch(items)
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
    contacts = parse_vcf(raw)
    if not contacts:
        raise HTTPException(status_code=400, detail="Nenhum contato com telefone encontrado no .vcf.")
    svc = _svc(db, ctx)
    results = svc.sync_batch(contacts)
    created = sum(1 for r in results if r.get("action") == "created")
    updated = sum(1 for r in results if r.get("action") in ("updated", "unchanged"))
    # TELs além do principal/secundário do card: contados, nunca descartados
    # em silêncio (§8.4).
    ignorados = sum(int(c.get("telefones_ignorados") or 0) for c in contacts)
    # §9 etapa 8: o import não devolve mais uma linha por contato no JSON
    # (10k contatos = payload gigante). Só os contadores — o detalhe por
    # contato vive no CRM, e o audit grava o before/after onde importa.
    return {
        "imported": len(results),
        "created": created,
        "updated": updated,
        "telefones_ignorados": ignorados,
    }


@router.get("/export-vcf")
def export_vcf(
    formatar_rota: bool = False,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Exporta os clientes do tenant como arquivo .vcf.

    `formatar_rota=true` grava o nome de rota (etapa 7 / D5) no lugar do nome
    atual — o operador confere o resultado do renomeador SEM aplicar nada no
    CRM (fecha a lacuna G7 da auditoria: “só export do CRM cru”).
    """
    from app.application.contacts.formatter import formatar_nome_rota

    repo = _repo(db, ctx)
    clients = repo.listar_todos()

    lines: List[str] = []
    for c in clients:
        display = c.nome or f"Contato {c.telefone}"
        if formatar_rota:
            display = formatar_nome_rota(c)
        lines.append("BEGIN:VCARD")
        lines.append("VERSION:3.0")
        lines.append(f"FN:{_vcf_escape(display)}")
        lines.append(f"N:{_vcf_escape(display)};;;;")
        lines.append(f"TEL;TYPE=CELL:+{c.telefone}")
        if c.rua and c.rua != "A definir":
            # Ordem do spec vCard: pobox;ext;rua;cidade;região;CEP;país — é o que
            # o parser estendido lê de volta (o formato antigo punha complemento
            # no slot da cidade e descartava bairro/CEP).
            adr = ";".join(
                [
                    "",
                    _vcf_escape(c.complemento or ""),
                    _vcf_escape(c.rua or ""),
                    _vcf_escape(c.bairro or ""),
                    "",
                    _vcf_escape(c.cep or ""),
                    "",
                ]
            )
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


# ── F6: Organizador de contatos (renomeador em lote + códigos + conflitos) ──


class RenameRule(BaseModel):
    """Regra de renomeação (espelha build_rename_rule do organizer)."""

    trim: bool = True
    strip_prefixes: bool = False
    prefixes: Optional[List[str]] = None
    case: Optional[str] = None  # "title" | "upper" | "lower" | None
    pattern_bairro: bool = False  # "Nome — Bairro"
    pattern_endereco: bool = False  # padrão de rota (etapa 7 / D5)


class RenameFilter(BaseModel):
    """Filtro da seleção do renomeador (preview/apply desacoplados — §6.4)."""

    search: Optional[str] = None
    bairro: Optional[str] = None
    status: Optional[str] = None  # OK | NAO_ENCONTRADO | PENDENTE | SEM_ENDERECO


class RenameApplyRequest(BaseModel):
    rule: RenameRule
    codes: List[str] = []
    filtro: Optional[RenameFilter] = None
    all_matching: bool = False
    # Nome visto no preview por código → trava anti-corrida (skipped_stale).
    expected: Optional[Dict[str, str]] = None


class ContactJobRequest(BaseModel):
    """Criação de job bounded-batch do renomeador (Fase 2 §5, etapa 8)."""

    tipo: str  # GEOCODE | OVERPASS | APPLY
    filtro: Optional[RenameFilter] = None
    regra: Optional[RenameRule] = None


def _organizer(db: Session, ctx: TenantContext):
    from app.application.contacts.organizer import ContactOrganizer

    return ContactOrganizer(db, _repo(db, ctx), ctx.tenant_id)


@router.post("/organizer/rename-preview")
def organizer_rename_preview(
    rule: RenameRule,
    search: Optional[str] = None,
    bairro: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    # Default = 200 para paridade exata com o preview antigo: a UI legada ainda
    # envia `codes` a partir desta página, então mudar o default seria uma
    # quebra silenciosa. A UI paginada (Fase 2 §13) passa `page_size` explícito.
    page_size: int = 200,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("customer.update")),
):
    """Preview PAGINADO do renomeador — calcula mudanças SEM gravar (I3).

    Sem teto: varre toda a base que casa com `search`/`bairro`/`status` e
    devolve só a página pedida + `total`. Contatos em conflito ("Revisar")
    ficam fora do preview: nada automático sobre contato conflitante.
    """
    from app.application.contacts.organizer import build_rename_rule

    try:
        validated = build_rename_rule(
            trim=rule.trim,
            strip_prefixes=rule.strip_prefixes,
            prefixes=rule.prefixes,
            case=rule.case,
            pattern_bairro=rule.pattern_bairro,
            pattern_endereco=rule.pattern_endereco,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _organizer(db, ctx).preview_rename(
        validated,
        search=search or "",
        filtro={"bairro": bairro, "status": status},
        page=page,
        page_size=page_size,
    )


@router.post("/organizer/rename-apply")
def organizer_rename_apply(
    payload: RenameApplyRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("customer.update")),
):
    """Aplica renomeações confirmadas (preview/apply desacoplados — §6.4).

    Aceita três formas de seleção (§6.4), nunca “aplicar a todos” implícito:
    `codes` (contrato legado), `filtro` ou `all_matching=True`. Grava audit
    `contact.rename` (before/after) por contato alterado.
    """
    from app.application.contacts.organizer import build_rename_rule

    try:
        validated = build_rename_rule(
            trim=payload.rule.trim,
            strip_prefixes=payload.rule.strip_prefixes,
            prefixes=payload.rule.prefixes,
            case=payload.rule.case,
            pattern_bairro=payload.rule.pattern_bairro,
            pattern_endereco=payload.rule.pattern_endereco,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    filtro = payload.filtro
    try:
        return _organizer(db, ctx).apply_rename(
            validated,
            codes=payload.codes or None,
            actor_id=ctx.user_id,
            filtro={"bairro": filtro.bairro, "status": filtro.status} if filtro else None,
            all_matching=payload.all_matching,
            expected=payload.expected,
            search=(filtro.search if filtro else None) or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/organizer/backfill-codes")
def organizer_backfill_codes(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("customer.update")),
):
    """Backfill: atribui código sequencial global a contatos sem código (I1).

    Idempotente: segunda execução sem novos contatos retorna fixed=0.
    """
    return _organizer(db, ctx).backfill_codes(actor_id=ctx.user_id)


@router.get("/organizer/conflicts")
def organizer_conflicts(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Lista "Revisar": contatos em conflito (nome duplicado / telefone divergente).

    Apenas sinaliza (I3) — correção é sempre manual, contato por contato.
    """
    return _organizer(db, ctx).list_conflicts()


@router.get("/organizer/geocode-origem")
def organizer_geocode_origem(
    limite: int = 100,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Origem do geocode: OSM × fallback de CEP (etapa 9 / ADR-0007).

    A triagem do renomeador mostra de onde cada endereço veio — o ponto do
    fallback de CEP é de *trecho*, não tem a qualidade do logradouro do OSM, e
    quem aplica o lote precisa saber em qual dos dois está pisando.
    """
    return _organizer(db, ctx).geocode_origem(limite=limite)


# ═══════════════════════════════════════════════════════════
# Jobs bounded-batch (Fase 2 §5, etapa 8)
# ═══════════════════════════════════════════════════════════


def _job_service(db: Session, ctx: TenantContext):
    from app.application.contacts.jobs import ContactJobService

    return ContactJobService(db, _repo(db, ctx), ctx.tenant_id)


def _validar_regra(rule: RenameRule) -> Dict:
    from app.application.contacts.organizer import build_rename_rule

    try:
        return build_rename_rule(
            trim=rule.trim,
            strip_prefixes=rule.strip_prefixes,
            prefixes=rule.prefixes,
            case=rule.case,
            pattern_bairro=rule.pattern_bairro,
            pattern_endereco=rule.pattern_endereco,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/jobs", dependencies=[Depends(require_renamer_enabled)])
def contact_job_create(
    payload: ContactJobRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("customer.update")),
):
    """Cria um job do renomeador (GEOCODE | OVERPASS | APPLY).

    Gated por `CONTACT_RENAMER_ENABLED` (409 quando desligado). O job é
    retomável pelo cursor; o avanço acontece em `/jobs/{id}/process`.
    """
    filtro = payload.filtro.model_dump() if payload.filtro else None
    regra = _validar_regra(payload.regra) if payload.regra is not None else None
    try:
        return _job_service(db, ctx).criar_job(payload.tipo, filtro=filtro, regra=regra)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/jobs/{job_id}/process", dependencies=[Depends(require_renamer_enabled)])
def contact_job_process(
    job_id: str,
    limite: Optional[int] = None,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("customer.update")),
):
    """Processa a PRÓXIMA faixa do job (bounded-batch) e devolve o progresso.

    Chamar de novo continua de onde parou. Quando a faixa vem incompleta, o
    job passa a `CONCLUIDO`.
    """
    try:
        return _job_service(db, ctx).processar_proximo_lote(job_id, limite=limite)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/jobs/{job_id}", dependencies=[Depends(require_renamer_enabled)])
def contact_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("customer.update")),
):
    """Status/progresso do job (inclui a métrica do passe Overpass)."""
    try:
        return _job_service(db, ctx).status(job_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


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
