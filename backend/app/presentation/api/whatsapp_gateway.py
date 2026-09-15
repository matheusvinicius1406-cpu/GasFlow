"""
WhatsApp Gateway API — FASE 10

Endpoints for:
- POST /whatsapp/incoming — Process incoming WhatsApp message
- GET /whatsapp/conversations — List conversations
- GET /whatsapp/conversations/{id} — Get conversation detail
- POST /whatsapp/conversations/{id}/takeover — Operator takeover
- POST /whatsapp/conversations/{id}/release — Release to AI
- POST /whatsapp/conversations/{id}/reply — Operator manual reply
- GET /whatsapp/stats — Conversation statistics
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from app.presentation.dependencies import get_tenant_context, require_whatsapp_service_or_user
from app.domain.security.models import TenantContext
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
from app.infrastructure.database.dependencies import get_db
from app.infrastructure.whatsapp.repositories import (
    SQLAlchemyConversationRepository,
    SQLAlchemyConversationMessageRepository,
)
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.infrastructure.ai.factory import get_llm_provider
from app.application.ai.engine import AIEngine
from app.application.ai.tools_impl import AIToolsFactory
from app.application.whatsapp.gateway import MessageGateway, OperatorGateway
from app.domain.whatsapp.conversation import ConversationMessage, ConversationState
from app.domain.ai.tools import ToolRegistry, ToolDefinition, ToolType, ToolPermission

router = APIRouter(prefix="/whatsapp", tags=["whatsapp-conversations"])


# ── Schemas ──────────────────────────────────────────────


class IncomingMessageRequest(BaseModel):
    account_id: str = Field("primary")
    sender_phone: str = Field(..., min_length=8, max_length=20)
    provider_message_id: str = Field(..., min_length=1, max_length=200)
    text: str = Field("", max_length=4096)
    message_type: str = Field("TEXT")
    from_me: bool = False
    timestamp: Optional[str] = None
    sender_name: Optional[str] = Field(None, max_length=120)


class IncomingMessageResponse(BaseModel):
    status: str
    conversation_id: Optional[int] = None
    outbound_text: Optional[str] = None
    outbound_to: Optional[str] = None
    error: Optional[str] = None


class ConversationInfo(BaseModel):
    id: int
    account_id: str
    customer_phone: str
    customer_codigo: Optional[str] = None
    contact_name: Optional[str] = None
    state: str
    human_operator: Optional[str] = None
    message_count: int = 0
    last_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ConversationDetail(BaseModel):
    id: int
    account_id: str
    customer_phone: str
    customer_codigo: Optional[str] = None
    contact_name: Optional[str] = None
    state: str
    human_operator: Optional[str] = None
    draft: Optional[Dict[str, Any]] = None
    messages: List[Dict[str, Any]] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TakeoverRequest(BaseModel):
    operator: str = Field(..., min_length=1, max_length=100)


class ReplyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096)


# ── Helpers ──────────────────────────────────────────────


def _build_tool_registry(db) -> ToolRegistry:
    """Build tool registry for AI engine."""
    registry = ToolRegistry()
    factory = AIToolsFactory(db_session=db)

    registry.register(
        ToolDefinition(
            name="get_customer",
            description="Buscar cliente",
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
            description="Buscar clientes",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            handler=factory.search_customers,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_customer_360",
            description="Customer 360",
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
            description="Buscar pedido",
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
            description="Consultar estoque",
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
            description="Resumo do estoque",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={"type": "object", "properties": {}},
            handler=factory.get_inventory_summary,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_payments",
            description="Pagamentos",
            tool_type=ToolType.READ,
            permission=ToolPermission.READ_ONLY,
            input_schema={"type": "object", "properties": {"order_codigo": {"type": "string"}}},
            handler=factory.get_payments,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_receivables",
            description="Contas a receber",
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
                    "delivery_fee": {"type": "number"},
                    "discount": {"type": "number"},
                },
                "required": ["client_codigo", "items"],
            },
            handler=factory.create_order,
        )
    )
    registry.register(
        ToolDefinition(
            name="add_stock",
            description="Adicionar estoque (requer confirmação)",
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
                    "idempotency_key": {"type": "string"},
                },
                "required": ["order_codigo", "amount", "method"],
            },
            handler=factory.register_payment,
        )
    )
    registry.register(
        ToolDefinition(
            name="update_client_address",
            description="Atualizar endereço do cliente (requer confirmação)",
            tool_type=ToolType.WRITE,
            permission=ToolPermission.OPERATOR,
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "phone": {"type": "string"},
                    "customer_codigo": {"type": "string"},
                    "rua": {"type": "string"},
                    "numero": {"type": "string"},
                    "complemento": {"type": "string"},
                    "bairro": {"type": "string"},
                    "referencia": {"type": "string"},
                },
            },
            handler=factory.update_client_address,
        )
    )
    return registry


# ── Endpoints ────────────────────────────────────────────


@router.post("/incoming", response_model=IncomingMessageResponse)
async def process_incoming(
    req: IncomingMessageRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_whatsapp_service_or_user),
):
    """Process incoming WhatsApp message through AI pipeline."""

    conv_repo = SQLAlchemyConversationRepository(db)
    msg_repo = SQLAlchemyConversationMessageRepository(db)
    registry = _build_tool_registry(db)
    ai_engine = AIEngine(llm_provider=get_llm_provider(), tool_registry=registry)

    # Get repositories for customer/product resolution
    from app.infrastructure.repositories.product_repository import SQLAlchemyProductRepository
    from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository

    gateway = MessageGateway(
        conversation_repo=conv_repo,
        message_repo=msg_repo,
        ai_engine=ai_engine,
        customer_repository=SQLAlchemyClientRepository(db),
        product_repository=SQLAlchemyProductRepository(db),
        inventory_repository=SQLAlchemyInventoryRepository(db),
    )

    result = gateway.process_incoming(
        {
            "account_id": req.account_id,
            "sender_phone": req.sender_phone,
            "provider_message_id": req.provider_message_id,
            "text": req.text,
            "message_type": req.message_type,
            "from_me": req.from_me,
            "sender_name": req.sender_name,
        }
    )

    outbound = result.get("outbound")
    return IncomingMessageResponse(
        status=result.get("status", "error"),
        conversation_id=result.get("conversation_id"),
        outbound_text=outbound.text if outbound else None,
        outbound_to=outbound.recipient_phone if outbound else None,
        error=result.get("error"),
    )


@router.get("/conversations")
async def list_conversations(
    account_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List active WhatsApp conversations."""

    conv_repo = SQLAlchemyConversationRepository(db)
    msg_repo = SQLAlchemyConversationMessageRepository(db)
    conversations, total = conv_repo.list_active(account_id=account_id, limit=limit, offset=offset)

    # Nome do contato: resolved do cadastro de clientes (cache por telefone).
    client_repo = SQLAlchemyClientRepository(db)
    name_cache: Dict[str, Optional[str]] = {}

    def _contact_name(phone: str) -> Optional[str]:
        if phone not in name_cache:
            client = client_repo.buscar_por_telefone(phone)
            name_cache[phone] = client.nome if client and client.nome else None
        return name_cache[phone]

    items = []
    for conv in conversations:
        messages = msg_repo.list_by_conversation(conv.id, limit=1, offset=0)
        last_msg = messages[-1].content if messages else None
        msg_count = msg_repo.count_by_conversation(conv.id)
        items.append(
            ConversationInfo(
                id=conv.id,
                account_id=conv.account_id,
                customer_phone=conv.customer_phone,
                customer_codigo=conv.customer_codigo,
                contact_name=_contact_name(conv.customer_phone),
                state=conv.state.value,
                human_operator=conv.human_operator,
                message_count=msg_count,
                last_message=last_msg[:200] if last_msg else None,
                created_at=conv.created_at.isoformat() if conv.created_at else None,
                updated_at=conv.updated_at.isoformat() if conv.updated_at else None,
            ).model_dump()
        )
    return {"conversations": items, "total": total}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: int, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context)
):
    """Get conversation detail with messages."""

    conv_repo = SQLAlchemyConversationRepository(db)
    msg_repo = SQLAlchemyConversationMessageRepository(db)
    conv = conv_repo.find_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")

    contact_name = None
    if conv.customer_codigo:
        client = SQLAlchemyClientRepository(db).buscar_por_codigo(conv.customer_codigo)
        contact_name = client.nome if client and client.nome else None
    if not contact_name:
        client = SQLAlchemyClientRepository(db).buscar_por_telefone(conv.customer_phone)
        contact_name = client.nome if client and client.nome else None

    messages = msg_repo.list_by_conversation(conversation_id, limit=200)
    msg_list = [
        {
            "id": m.id,
            "direction": m.direction,
            "sender": m.sender,
            "content": m.content,
            "message_type": m.message_type,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]

    return ConversationDetail(
        id=conv.id,
        account_id=conv.account_id,
        customer_phone=conv.customer_phone,
        customer_codigo=conv.customer_codigo,
        contact_name=contact_name,
        state=conv.state.value,
        human_operator=conv.human_operator,
        draft=conv.draft.to_dict() if conv.draft else None,
        messages=msg_list,
        created_at=conv.created_at.isoformat() if conv.created_at else None,
        updated_at=conv.updated_at.isoformat() if conv.updated_at else None,
    ).model_dump()


@router.post("/conversations/{conversation_id}/takeover")
async def takeover_conversation(
    conversation_id: int,
    req: TakeoverRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Operator takes over conversation."""

    conv_repo = SQLAlchemyConversationRepository(db)
    msg_repo = SQLAlchemyConversationMessageRepository(db)
    operator_gw = OperatorGateway(conv_repo, msg_repo)
    result = operator_gw.takeover(conversation_id, req.operator)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"success": True, "message": f"Operador {req.operator} assumiu a conversa."}


@router.post("/conversations/{conversation_id}/release")
async def release_conversation(
    conversation_id: int, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context)
):
    """Release conversation back to AI."""

    conv_repo = SQLAlchemyConversationRepository(db)
    msg_repo = SQLAlchemyConversationMessageRepository(db)
    operator_gw = OperatorGateway(conv_repo, msg_repo)
    result = operator_gw.release_to_ai(conversation_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"success": True, "message": "Conversa devolvida à IA."}


@router.post("/conversations/{conversation_id}/reply")
async def operator_reply(
    conversation_id: int,
    req: ReplyRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Operator sends manual reply — ENVIA de verdade via serviço WhatsApp.

    Fix (docs/whatsapp-fix-spec.md): antes só persistia no banco e fingia
    sucesso — a mensagem nunca chegava ao cliente. Agora:
    1. Auto-assume a conversa se não estiver em atendimento humano;
    2. Envia via serviço WhatsApp (proxy);
    3. Só persiste a mensagem se o envio teve sucesso;
    4. Propaga erro de envio (não finge mais que enviou).
    """

    conv_repo = SQLAlchemyConversationRepository(db)
    msg_repo = SQLAlchemyConversationMessageRepository(db)

    conv = conv_repo.find_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="CONVERSATION_NOT_FOUND")
    if conv.state == ConversationState.CLOSED:
        raise HTTPException(status_code=400, detail="CONVERSATION_CLOSED")

    # 1. Auto-assumir: responder manualmente implica atendimento humano.
    if conv.state != ConversationState.HUMAN_ACTIVE:
        conv_repo.takeover(conversation_id, "Operador")

    # 2. Envio REAL via serviço WhatsApp.
    from app.presentation.api.whatsapp import _proxy_post

    send_result = await _proxy_post(
        f"/whatsapp/accounts/{conv.account_id}/messages",
        {"recipient": conv.customer_phone, "message": req.text},
    )
    if not isinstance(send_result, dict) or not send_result.get("success"):
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao enviar via WhatsApp: {send_result}",
        )

    # 3. Persistir após sucesso (sender=human; inclui o messageId real).
    msg_repo.create(
        ConversationMessage(
            conversation_id=conversation_id,
            direction="OUTGOING",
            sender="human",
            content=req.text,
            message_type="TEXT",
            metadata={
                "provider_message_id": send_result.get("messageId"),
                "origin": "operator_reply",
            },
        )
    )
    return {"success": True, "message": "Resposta enviada."}


@router.get("/stats")
async def get_stats(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context)):
    """Get conversation statistics."""

    conv_repo = SQLAlchemyConversationRepository(db)
    return {
        "active_conversations": conv_repo.count_active(),
        "by_account": {a: conv_repo.count_active(account_id=a) for a in ["primary", "secondary"]},
    }
