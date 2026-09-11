"""
AI API Endpoints — FASE 9

POST /ai/chat — Main chat endpoint
GET /ai/conversations — List conversations
GET /ai/conversations/{id} — Get conversation with messages
GET /ai/tools — List available tools
GET /ai/audit — Get audit log
"""

import uuid
from fastapi import APIRouter, HTTPException, Depends
from app.presentation.dependencies import get_tenant_context
from app.domain.security.models import TenantContext
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
from app.infrastructure.database.dependencies import get_db
from app.infrastructure.ai.factory import get_llm_provider
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
