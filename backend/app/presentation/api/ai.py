"""
AI API Endpoints — FASE 9 + Item 3

POST /ai/chat — Main chat endpoint
GET /ai/conversations — List conversations
GET /ai/conversations/{id} — Get conversation with messages
GET /ai/tools — List available tools
GET /ai/audit — Get audit log

Item 3 (IA no boot, toggle admin, sem jargão na UI):
GET   /ai/status                   — status p/ o dono (ai.use)
POST  /ai/test                     — prompt de teste (ai.use)
GET   /ai/settings                 — config completa (ai.configure)
PATCH /ai/settings                 — atualiza toggle/modelo/timeout (ai.configure)
POST  /ai/model/download           — dispara pull no Ollama (ai.configure)
GET   /ai/model/download-progress  — progresso do pull (polling JSON)

Cenário B da Fase 4.2: NÃO há provider externo de fallback — quando o
Ollama local não responde, a IA degrada com mensagem controlada.
"""

import hashlib
import json
import threading
import time
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from app.presentation.dependencies import get_tenant_context, require_permission
from app.domain.security.models import TenantContext
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
from app.infrastructure.database.dependencies import get_db
from app.core.config import settings
from app.infrastructure.ai.factory import get_llm_provider, is_ollama_healthy, reset_health_cache
from app.infrastructure.ai.repositories import SQLAlchemyConversationRepository, SQLAlchemyMessageRepository
from app.application.ai.engine import AIEngine
from app.application.ai.tools_impl import AIToolsFactory
from app.domain.ai.tools import ToolRegistry, ToolDefinition, ToolType, ToolPermission

router = APIRouter(prefix="/ai", tags=["ai"])

# ── Pydantic Schemas ──────────────────────────────────


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[str] = None
    # DEPRECATED: aceito por compatibilidade de contrato mas IGNORADO.
    # O nível de permissão é derivado do papel autenticado no servidor —
    # o cliente não escolhe o próprio nível (controle de acesso quebrado).
    permission_level: Optional[str] = Field(
        None, description="Ignored — derived server-side from the authenticated role"
    )


class ChatResponse(BaseModel):
    message: str
    intent: Optional[str] = None
    requires_confirmation: bool = False
    tool_used: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    conversation_id: Optional[str] = None


class ToolInfo(BaseModel):
    name: str
    description: str
    tool_type: str
    permission: str
    requires_confirmation: bool


class ConversationInfo(BaseModel):
    external_id: str
    title: Optional[str] = None
    created_at: Optional[str] = None
    message_count: int = 0


class AuditEntry(BaseModel):
    request_id: str
    conversation_id: Optional[str] = None
    intent: Optional[str] = None
    tool: Optional[str] = None
    confidence: Optional[str] = None
    success: Optional[bool] = None
    latency_ms: Optional[float] = None
    model: Optional[str] = None
    timestamp: Optional[str] = None


# ── Role → permission level mapping ──────────────────


def _role_to_permission_level(ctx: TenantContext) -> str:
    """Deriva o nível de permissão IA do papel autenticado (server-side).

    ADMIN/MANAGER → ADMIN; OPERATOR (atendente) → OPERATOR;
    DRIVER/CUSTOMER (PIN baixo privilégio) → READ_ONLY. Chamadores de
    serviço (whatsapp gateway) mantêm OPERATOR — o gateway já limita as
    ferramentas expostas ao canal de mensagens.
    """
    from app.domain.security.models import SystemRole

    if ctx.role in (SystemRole.ADMIN, SystemRole.MANAGER, SystemRole.SYSTEM):
        return "ADMIN"
    if ctx.role == SystemRole.OPERATOR:
        return "OPERATOR"
    return "READ_ONLY"


# ── Tool Registry Setup ───────────────────────────────


def _build_tool_registry(db: Optional[Session] = None) -> ToolRegistry:
    """Build the tool registry with all available tools.

    Todas as tools recebem handler (AIToolsFactory) — sem handler a tool
    sempre falhava com "Tool has no handler" e o endpoint principal de chat
    só respondia perguntas genéricas.
    """
    registry = ToolRegistry()
    factory = AIToolsFactory(db_session=db)

    # READ TOOLS
    registry.register(
        ToolDefinition(
            name="get_customer",
            description="Buscar cliente por código, nome ou telefone",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={
                "type": "object",
                "properties": {
                    "customer_codigo": {"type": "string"},
                    "customer_name": {"type": "string"},
                    "phone": {"type": "string"},
                },
            },
            handler=factory.get_customer,
        )
    )
    registry.register(
        ToolDefinition(
            name="search_customers",
            description="Buscar clientes com filtros",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            handler=factory.search_customers,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_customer_360",
            description="Customer 360 com métricas",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={
                "type": "object",
                "properties": {"customer_codigo": {"type": "string"}},
                "required": ["customer_codigo"],
            },
            handler=factory.get_customer_360,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_order",
            description="Buscar pedido por código",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={
                "type": "object",
                "properties": {"order_codigo": {"type": "string"}},
                "required": ["order_codigo"],
            },
            handler=factory.get_order,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_inventory",
            description="Consultar estoque de um produto",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={
                "type": "object",
                "properties": {"product_codigo": {"type": "string"}},
                "required": ["product_codigo"],
            },
            handler=factory.get_inventory,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_low_stock",
            description="Produtos com estoque baixo",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={"type": "object", "properties": {}},
            handler=factory.get_low_stock,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_inventory_summary",
            description="Resumo do inventário",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={"type": "object", "properties": {}},
            handler=factory.get_inventory_summary,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_payments",
            description="Consultar pagamentos",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={"type": "object", "properties": {"order_codigo": {"type": "string"}}},
            handler=factory.get_payments,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_receivables",
            description="Consultar contas a receber",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={"type": "object", "properties": {"customer_codigo": {"type": "string"}}},
            handler=factory.get_receivables,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_financial_summary",
            description="Resumo financeiro",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={"type": "object", "properties": {}},
            handler=factory.get_financial_summary,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_sales_summary",
            description="Resumo de vendas",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={"type": "object", "properties": {}},
            handler=factory.get_sales_summary,
        )
    )
    registry.register(
        ToolDefinition(
            name="search_products",
            description="Buscar produtos",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            handler=factory.search_products,
        )
    )

    # WRITE TOOLS
    registry.register(
        ToolDefinition(
            name="create_order",
            description="Criar pedido (requer confirmação)",
            tool_type=ToolType.WRITE,
            permission=ToolPermission.OPERATOR,
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "client_codigo": {"type": "string"},
                    "items": {"type": "array"},
                },
                "required": ["client_codigo", "items"],
            },
            handler=factory.create_order,
        )
    )
    registry.register(
        ToolDefinition(
            name="add_stock",
            description="Entrada de estoque (requer confirmação)",
            tool_type=ToolType.WRITE,
            permission=ToolPermission.OPERATOR,
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "product_codigo": {"type": "string"},
                    "quantity": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["product_codigo", "quantity"],
            },
            handler=factory.add_stock,
        )
    )
    registry.register(
        ToolDefinition(
            name="register_payment",
            description="Registrar pagamento (requer confirmação)",
            tool_type=ToolType.WRITE,
            permission=ToolPermission.OPERATOR,
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "order_codigo": {"type": "string"},
                    "amount": {"type": "number"},
                    "method": {"type": "string"},
                },
                "required": ["order_codigo", "amount", "method"],
            },
            handler=factory.register_payment,
        )
    )
    # ── F4: Referral tools ─────────────────────────────
    registry.register(
        ToolDefinition(
            name="register_referral",
            description="Registrar cliente novo via token de convite de indicação",
            tool_type=ToolType.WRITE,
            permission=ToolPermission.PUBLIC_WRITE,  # auto-cadastro público via token
            input_schema={
                "type": "object",
                "properties": {
                    "invite_token": {"type": "string"},
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "rua": {"type": "string"},
                    "numero": {"type": "string"},
                    "bairro": {"type": "string"},
                    "tenant_id": {"type": "string"},
                    "ip": {"type": "string"},
                },
                "required": ["invite_token", "name", "phone"],
            },
            handler=factory.register_referral,
        )
    )
    registry.register(
        ToolDefinition(
            name="list_client_coupons",
            description="Listar cupons ativos do cliente (disponíveis para usar)",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={
                "type": "object",
                "properties": {
                    "customer_codigo": {"type": "string"},
                    "tenant_id": {"type": "string"},
                },
                "required": ["customer_codigo"],
            },
            handler=factory.list_client_coupons,
        )
    )

    return registry


# ── Global instances (lazy init) ──────────────────────

_tool_registry = None
_engine = None


def _get_engine():
    """Engine singleton com registry construído uma única vez.

    IMPORTANTE: o registry é construído com AIToolsFactory(db_session=None)
    — cada chamada de tool abre a própria SessionLocal e a fecha, evitando
    handlers amarrados a uma session de request que já foi fechada.
    """
    global _tool_registry, _engine
    if _engine is None:
        _tool_registry = _build_tool_registry(None)
        _engine = AIEngine(
            llm_provider=get_llm_provider(),
            tool_registry=_tool_registry,
        )
    return _engine


def _get_tools():
    global _tool_registry
    if _tool_registry is None:
        _get_engine()
    return _tool_registry


# ── Endpoints ─────────────────────────────────────────


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context)):
    """Main AI chat endpoint.

    O nível de permissão é derivado do papel autenticado (ctx) — o valor
    eventual enviado pelo cliente é ignorado (controle de acesso quebrado
    se o cliente escolhesse o próprio nível). Per-tool, a checagem acontece
    no engine (AIEngine._execute_tool), comparando tool.permission com este
    nível.
    """
    try:
        permission_level = _role_to_permission_level(ctx)
        engine = _get_engine()
        engine.conversation_repo = SQLAlchemyConversationRepository(db)
        engine.message_repo = SQLAlchemyMessageRepository(db)

        # Create or get conversation
        conv_id = request.conversation_id
        if not conv_id:
            conv_id = str(uuid.uuid4())
            conv_repo = SQLAlchemyConversationRepository(db)
            from app.domain.ai.conversation import Conversation

            conv_repo.create(Conversation(external_id=conv_id, title=request.message[:50]))

        result = engine.chat(
            message=request.message,
            conversation_id=conv_id,
            permission_level=permission_level,
        )

        return ChatResponse(
            message=result["message"],
            intent=result.get("intent"),
            requires_confirmation=result.get("requires_confirmation", False),
            tool_used=result.get("tool_used"),
            data=result.get("data"),
            error=result.get("error"),
            conversation_id=conv_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI processing error: {str(e)}") from e


@router.get("/tools", response_model=List[ToolInfo])
def list_tools():
    """List available AI tools."""
    registry = _get_tools()
    return [
        ToolInfo(
            name=t.name,
            description=t.description,
            tool_type=t.tool_type.value,
            permission=t.permission.value,
            requires_confirmation=t.requires_confirmation,
        )
        for t in registry.list_tools()
    ]


@router.get("/conversations", response_model=List[ConversationInfo])
def list_conversations(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context)):
    """List recent conversations."""
    repo = SQLAlchemyConversationRepository(db)
    convs = repo.list_all(limit=20)
    return [
        ConversationInfo(
            external_id=c.external_id,
            title=c.title,
            created_at=c.created_at.isoformat() if c.created_at else None,
            message_count=len(c.messages),
        )
        for c in convs
    ]


@router.get("/audit")
def get_audit_log(limit: int = 50, ctx: TenantContext = Depends(get_tenant_context)):
    """Get AI audit log."""
    engine = _get_engine()
    return engine.get_audit_log(limit=limit)


# ═════════════════════════════════════════════════════════
#  Item 3 — Status / Teste / Config da IA (sem jargão na UI)
# ═════════════════════════════════════════════════════════


def _ai_audit(
    db: Session,
    ctx: TenantContext,
    action: str,
    resource_id: str = "",
    details: Optional[Dict[str, Any]] = None,
    result: str = "SUCCESS",
    before_json: Optional[Dict[str, Any]] = None,
    after_json: Optional[Dict[str, Any]] = None,
) -> None:
    """Audit trail de IA (best-effort, convenção P0 3.3).

    NUNCA grava conteúdo de prompt/resposta — só metadados (latência,
    provider, hash do prompt quando aplicável).
    """
    try:
        from app.infrastructure.repositories.auth_model import AuthAuditModel

        db.add(
            AuthAuditModel(
                id=str(uuid.uuid4()),
                actor_id=ctx.user_id,
                actor_type="USER",
                tenant_id=ctx.tenant_id,
                action=action,
                resource="ai",
                resource_id=resource_id,
                result=result,
                timestamp=datetime.utcnow(),
                ip_address="",
                user_agent="",
                platform="backend",
                details=details,
                before_json=before_json,
                after_json=after_json,
            )
        )
        db.commit()
    except Exception:  # pragma: no cover — audit nunca derruba a operação
        db.rollback()


class AiStatus(BaseModel):
    # Texto pronto para a UI — sem "Ollama", sem "qwen3" (guard 3.6).
    state: str = Field(description="ready | preparing | unavailable | disabled")
    message: str
    progress: Optional[int] = None
    provider: str = Field(description="local | none — nunca exposto na UI principal")


class AiTestRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)


class AiTestResponse(BaseModel):
    response: str
    provider: str = Field(description="local | online | none")
    error: Optional[str] = None


class AiSettingsIn(BaseModel):
    enabled: Optional[bool] = None
    model: Optional[str] = Field(default=None, max_length=100)
    timeout_seconds: Optional[int] = Field(default=None, ge=5, le=300)


class AiSettingsOut(BaseModel):
    enabled: bool
    provider: str
    model: str
    timeout_seconds: int
    last_health_check: Optional[str] = None


def _ai_enabled_from_db(db: Session) -> bool:
    from app.application.settings.settings_service import SettingsService

    return bool(SettingsService(db).get_value("ai.enabled", True))


def _ai_settings_from_db(db: Session) -> AiSettingsOut:
    from app.application.settings.settings_service import SettingsService

    svc = SettingsService(db)
    return AiSettingsOut(
        enabled=bool(svc.get_value("ai.enabled", True)),
        provider=settings.ai_provider,
        model=settings.ollama_model,
        timeout_seconds=settings.ai_timeout_seconds,
        last_health_check=None,
    )


@router.get("/status", response_model=AiStatus)
def ai_status(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("ai.use")),
):
    """Status da IA para o dono do depósito — sem termos técnicos.

    Estado derivado: disabled (toggle off) → ready (Ollama respondeu) →
    unavailable (Ollama não respondeu).    "preparing" é emitido pelo desktop durante o download do modelo via IPC (não vem daqui).
    """
    if not _ai_enabled_from_db(db):
        return AiStatus(state="disabled", message="Inteligência desativada nas configurações.", provider="none")

    if settings.ai_provider == "mock":
        return AiStatus(state="ready", message="IA pronta (modo demonstração).", provider="local")

    if is_ollama_healthy():
        return AiStatus(state="ready", message="IA pronta.", provider="local")
    return AiStatus(state="unavailable", message="IA temporariamente indisponível.", provider="none")


@router.post("/test", response_model=AiTestResponse)
def ai_test(
    body: AiTestRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("ai.use")),
):
    """Teste rápido: envia um prompt ao provider ativo e devolve a resposta.

    Auditoria registra provider + latência + hash do prompt — nunca o
    conteúdo (regra de privacidade do Item 3).
    """
    start = time.monotonic()
    enabled = _ai_enabled_from_db(db)
    provider = get_llm_provider()
    from app.domain.ai.provider import LLMMessage, LLMRole

    result = provider.generate([LLMMessage(role=LLMRole.USER, content=body.prompt)])
    latency_ms = (time.monotonic() - start) * 1000
    provider_label = "local" if provider.model_name != "none" else "none"

    _ai_audit(
        db,
        ctx,
        action="ai.test.prompt",
        details={
            "provider": provider_label,
            "model": provider.model_name,
            "latency_ms": round(latency_ms, 1),
            "prompt_hash": hashlib.sha256(body.prompt.encode("utf-8")).hexdigest()[:16],
            "success": result.error is None,
        },
        result="SUCCESS" if result.error is None else "FAILURE",
    )

    error = result.error
    if error or not enabled:
        if not enabled:
            message = "Inteligência desativada nas configurações."
        elif error is not None and (
            error in ("AI_DISABLED",) or error.startswith(("LLM_UNAVAILABLE", "LLM_HTTP_ERROR"))
        ):
            message = "IA temporariamente indisponível."
        else:
            message = error or "Erro desconhecido."
        return AiTestResponse(response="", provider=provider_label, error=message)
    return AiTestResponse(response=result.content, provider=provider_label)


@router.get("/settings", response_model=AiSettingsOut)
def get_ai_settings(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("ai.configure")),
):
    """Config completa da IA (tela Admin → Inteligência)."""
    return _ai_settings_from_db(db)


@router.patch("/settings", response_model=AiSettingsOut)
def patch_ai_settings(
    body: AiSettingsIn,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("ai.configure")),
):
    """Atualiza toggle da IA (e, no futuro, modelo/timeout por settings).

    Auditoria com snapshot before/after (convenção P0 3.3).
    """
    from app.application.settings.settings_service import SettingsService

    before = _ai_settings_from_db(db).model_dump()
    svc = SettingsService(db)
    if body.enabled is not None:
        svc.update("ai.enabled", bool(body.enabled), updated_by=ctx.user_id)
    reset_health_cache()
    after = _ai_settings_from_db(db).model_dump()
    _ai_audit(db, ctx, action="ai.settings.changed", before_json=before, after_json=after)
    return _ai_settings_from_db(db)


# ── Download de modelo (pull) — polling simples, sem SSE ──

_download_state: Dict[str, Any] = {"active": False, "percent": None, "error": None}
_download_lock = threading.Lock()


@router.post("/model/download", status_code=202)
def download_model(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("ai.configure")),
):
    """Dispara `POST /api/pull` no Ollama em background (retorna 202).

    Cenário B: o modelo só vem do Ollama local — não há download externo.
    Progresso via GET /ai/model/download-progress (polling).
    """
    import httpx

    if not _ai_enabled_from_db(db):
        raise HTTPException(status_code=409, detail="IA desativada nas configurações.")
    with _download_lock:
        if _download_state["active"]:
            return {"started": False, "detail": "Download já em andamento."}
        _download_state.update({"active": True, "percent": 0, "error": None})

    model = settings.ollama_model

    def _pull() -> None:
        try:
            with httpx.Client(timeout=3600.0) as client:
                with client.stream(
                    "POST", f"{settings.ollama_base_url.rstrip('/')}/api/pull", json={"name": model}
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except ValueError:
                            continue
                        total = data.get("total") or 0
                        done = data.get("completed") or 0
                        if total:
                            _download_state["percent"] = min(99, int(done * 100 / total))
                        if data.get("error"):
                            _download_state["error"] = str(data["error"])[:200]
            _download_state["percent"] = 100
            reset_health_cache()
        except Exception as exc:  # noqa: BLE001 — erro vira estado, não exceção
            _download_state["error"] = f"Download falhou: {type(exc).__name__}"
        finally:
            with _download_lock:
                _download_state["active"] = False

    threading.Thread(target=_pull, daemon=True, name="ai-model-pull").start()
    _ai_audit(db, ctx, action="ai.model.download", resource_id=model)
    return {"started": True, "model": model}


@router.get("/model/download-progress")
def download_progress(ctx: TenantContext = Depends(require_permission("ai.configure"))):
    """Progresso do pull (polling JSON — simples e suficiente p/ Electron)."""
    return dict(_download_state)
