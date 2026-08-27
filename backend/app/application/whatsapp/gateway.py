"""
Message Gateway — FASE 10

Processes incoming WhatsApp messages:
1. Validate schema
2. Normalize phone
3. Deduplication
4. Resolve customer
5. Check ownership
6. Route to AI or human
7. Build response
8. Return outbound message

Architecture: WhatsApp → Message Gateway → Conversation → AI Core → Tools → Use Cases → Domain
"""

import json
import hashlib
import time
import re
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from app.domain.whatsapp.message import WhatsAppMessage, WhatsAppOutbound, MessageType
from app.domain.whatsapp.conversation import (
    Conversation, ConversationState, ConversationDraft, ConversationMessage,
)
from app.domain.whatsapp.repository import ConversationRepository, ConversationMessageRepository
from app.domain.ai.tools import ToolRegistry
from app.application.ai.engine import AIEngine


# ── Anti-loop ────────────────────────────────────────────
LOOP_MARKER = "[AI]"

# ── Confirmation patterns ────────────────────────────────
CONFIRMATION_POSITIVE = re.compile(
    r"^\s*(sim|s[íi]|confirmo?|pode mandar|fechar pedido|pode fechar|"
    r"fecho|bora|beleza|ok|pode|aprovo?|confirmar)\s*[!?.]*\s*$",
    re.IGNORECASE,
)
CONFIRMATION_NEGATIVE = re.compile(
    r"^\s*(n[ãa]o|n[ãa]o quero|cancela|deixa pra l[áa]|desisto|esquece)\s*[!?.]*\s*$",
    re.IGNORECASE,
)
RESET_PATTERNS = re.compile(
    r"^\s*(come[cç]ar de novo|novo pedido|resetar|limpar)\s*[!?.]*\s*$",
    re.IGNORECASE,
)
HUMAN_REQUEST = re.compile(
    r"(falar com atendente|falar com humano|humano|atendente|pessoa real|suporte humano)",
    re.IGNORECASE,
)

# ── Media detection ──────────────────────────────────────
MEDIA_TYPE_MAP = {
    "image": MessageType.IMAGE,
    "audio": MessageType.AUDIO,
    "document": MessageType.DOCUMENT,
}


class MessageGateway:
    """
    Central message processing gateway.
    Orchestrates: validation → normalization → dedup → customer resolution
    → ownership check → AI routing → response building.
    """

    def __init__(
        self,
        conversation_repo: ConversationRepository,
        message_repo: ConversationMessageRepository,
        ai_engine: AIEngine,
        customer_repository=None,
        product_repository=None,
        inventory_repository=None,
    ):
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo
        self.ai_engine = ai_engine
        self.customer_repo = customer_repository
        self.product_repo = product_repository
        self.inventory_repo = inventory_repository

    def process_incoming(
        self,
        raw_message: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Process an incoming WhatsApp message through the full pipeline.

        Returns:
            {
                "status": "processed" | "skipped" | "error" | "human_handoff",
                "outbound": WhatsAppOutbound | None,
                "conversation_id": int | None,
                "error": str | None,
            }
        """
        # 1. Parse and validate
        message = self._parse_message(raw_message)
        if not message:
            return {"status": "error", "error": "MESSAGE_INVALID", "outbound": None}

        # 2. Anti-loop: skip messages from ourselves
        if message.from_me:
            return {"status": "skipped", "error": "FROM_ME", "outbound": None}

        # 3. Skip non-text messages for now
        if message.message_type != MessageType.TEXT:
            return self._handle_media_message(message)

        # 4. Skip empty messages
        if not message.text or not message.text.strip():
            return {"status": "skipped", "error": "EMPTY_MESSAGE", "outbound": None}

        # 5. Find or create conversation
        conversation = self._get_or_create_conversation(message)

        # 6. Idempotency check
        if self.conversation_repo.find_duplicate_message(message.provider_message_id):
            return {"status": "skipped", "error": "DUPLICATE_MESSAGE", "conversation_id": conversation.id}

        # 7. Save incoming message
        incoming_msg = ConversationMessage(
            conversation_id=conversation.id,
            direction="INCOMING",
            sender="customer",
            content=message.text,
            message_type=message.message_type.value,
            metadata={"provider_message_id": message.provider_message_id},
        )
        self.message_repo.create(incoming_msg)

        # 8. Check if human operator is active
        if conversation.state == ConversationState.HUMAN_ACTIVE:
            return {"status": "human_active", "conversation_id": conversation.id, "outbound": None}

        # 9. Check for human handoff request
        if HUMAN_REQUEST.search(message.text):
            return self._request_human_handoff(conversation, message)

        # 10. Check for draft confirmation
        if conversation.draft and conversation.state == ConversationState.AWAITING_CONFIRMATION:
            return self._handle_confirmation(conversation, message)

        # 11. Check for draft cancellation
        if conversation.draft and CONFIRMATION_NEGATIVE.search(message.text):
            return self._cancel_draft(conversation, message)

        # 12. Check for reset
        if RESET_PATTERNS.search(message.text):
            return self._reset_conversation(conversation, message)

        # 13. Route through AI engine
        return self._route_to_ai(conversation, message)

    def _parse_message(self, raw: Dict[str, Any]) -> Optional[WhatsAppMessage]:
        """Parse and validate raw WhatsApp message."""
        try:
            account_id = raw.get("account_id", "primary")
            sender_phone = raw.get("sender_phone", "")
            text = raw.get("text", "")
            provider_message_id = raw.get("provider_message_id", "")
            message_type_str = raw.get("message_type", "TEXT")
            from_me = raw.get("from_me", False)

            if not sender_phone or not provider_message_id:
                return None

            # Normalize phone
            sender_phone = self._normalize_phone(sender_phone)
            if not sender_phone:
                return None

            msg_type = MessageType.TEXT
            for mt in MessageType:
                if mt.value == message_type_str.upper():
                    msg_type = mt
                    break

            return WhatsAppMessage(
                provider_message_id=provider_message_id,
                account_id=account_id,
                sender_phone=sender_phone,
                text=text.strip(),
                message_type=msg_type,
                from_me=from_me,
                raw=raw,
            )
        except Exception:
            return None

    def _normalize_phone(self, phone: str) -> Optional[str]:
        """Normalize phone to digits only."""
        digits = re.sub(r"\D", "", phone).lstrip("0")
        return digits if len(digits) >= 8 else None

    def _get_or_create_conversation(self, message: WhatsAppMessage) -> Conversation:
        """Find existing conversation or create new one."""
        existing = self.conversation_repo.find_by_phone_and_account(
            message.sender_phone, message.account_id
        )
        if existing:
            return existing

        new_conv = Conversation(
            account_id=message.account_id,
            customer_phone=message.sender_phone,
            state=ConversationState.IDLE,
        )
        return self.conversation_repo.create(new_conv)

    def _resolve_customer(self, phone: str) -> Optional[Dict[str, Any]]:
        """Resolve customer from phone number."""
        if not self.customer_repo:
            return None
        try:
            client = self.customer_repo.buscar_por_telefone(phone)
            if client:
                return {
                    "codigo": client.codigo,
                    "nome": client.nome,
                    "telefone": client.telefone,
                }
        except Exception:
            pass
        return None

    def _handle_media_message(self, message: WhatsAppMessage) -> Dict[str, Any]:
        """Handle non-text messages with a safe fallback."""
        conversation = self._get_or_create_conversation(message)
        reply = "Desculpe, no momento só consigo processar mensagens de texto. Pode digitar sua mensagem?"
        return self._build_outbound(conversation.id, message.sender_phone, message.account_id, reply)

    def _request_human_handoff(self, conversation: Conversation, message: WhatsAppMessage) -> Dict[str, Any]:
        """Transition to human handoff state."""
        conversation.transition_to(ConversationState.HUMAN_PENDING)
        self.conversation_repo.update_state(conversation.id, ConversationState.HUMAN_PENDING)
        reply = "Vou transferir para um atendente. Aguarde um momento."
        return {
            "status": "human_handoff",
            "conversation_id": conversation.id,
            "outbound": WhatsAppOutbound(
                recipient_phone=message.sender_phone,
                text=reply,
                account_id=message.account_id,
            ),
        }

    def _handle_confirmation(self, conversation: Conversation, message: WhatsAppMessage) -> Dict[str, Any]:
        """Handle order draft confirmation."""
        if CONFIRMATION_POSITIVE.search(message.text):
            # Execute order creation
            result = self._execute_order_creation(conversation)
            if result["success"]:
                return self._build_outbound(
                    conversation.id, conversation.customer_phone,
                    conversation.account_id, result["message"],
                )
            else:
                return self._build_outbound(
                    conversation.id, conversation.customer_phone,
                    conversation.account_id, result["message"],
                )
        elif CONFIRMATION_NEGATIVE.search(message.text):
            return self._cancel_draft(conversation, message)
        else:
            reply = "Não entendi se você confirma ou cancela. Pode digitar 'sim' ou 'não'?"
            return self._build_outbound(
                conversation.id, message.sender_phone,
                message.account_id, reply,
            )

    def _execute_order_creation(self, conversation: Conversation) -> Dict[str, Any]:
        """Execute order creation through AI tool → UseCase."""
        draft = conversation.draft
        if not draft or not draft.customer_codigo:
            return {"success": False, "message": "Draft inválido."}

        # Build items for CreateOrderUseCase
        items = []
        for item in draft.items:
            items.append({
                "product_codigo": item.get("product_codigo"),
                "quantity": item.get("quantity"),
            })

        # Use AI engine's tool to create order
        try:
            tool = self.ai_engine.tools.get("create_order")
            if tool and tool.handler:
                args = {
                    "client_codigo": draft.customer_codigo,
                    "items": items,
                    "delivery_fee": draft.delivery_fee,
                    "discount": draft.discount,
                    "notes": draft.notes or "",
                }
                result = tool.handler(args)
                if result.success:
                    # Transition state
                    conversation.transition_to(ConversationState.ORDER_CREATED)
                    self.conversation_repo.update_state(conversation.id, ConversationState.ORDER_CREATED)
                    self.conversation_repo.update_draft(conversation.id, None)
                    order_data = result.data
                    return {
                        "success": True,
                        "message": (
                            f"Pedido confirmado! "
                            f"Código: {order_data.get('order_codigo', '?')} "
                            f"Total: R$ {order_data.get('total', 0):.2f}"
                        ),
                    }
                else:
                    return {"success": False, "message": f"Erro ao criar pedido: {result.error}"}
            else:
                return {"success": False, "message": "Serviço de pedidos indisponível."}
        except Exception as e:
            return {"success": False, "message": f"Erro interno: {str(e)}"}

    def _cancel_draft(self, conversation: Conversation, message: WhatsAppMessage) -> Dict[str, Any]:
        """Cancel current order draft."""
        conversation.draft = None
        self.conversation_repo.update_draft(conversation.id, None)
        conversation.transition_to(ConversationState.BROWSING)
        self.conversation_repo.update_state(conversation.id, ConversationState.BROWSING)
        reply = "Pedido cancelado. Posso ajudar com mais alguma coisa?"
        return self._build_outbound(
            conversation.id, message.sender_phone,
            message.account_id, reply,
        )

    def _reset_conversation(self, conversation: Conversation, message: WhatsAppMessage) -> Dict[str, Any]:
        """Reset conversation state."""
        conversation.draft = None
        self.conversation_repo.update_draft(conversation.id, None)
        conversation.transition_to(ConversationState.IDLE)
        self.conversation_repo.update_state(conversation.id, ConversationState.IDLE)
        reply = "OK, recomeçamos. O que você precisa?"
        return self._build_outbound(
            conversation.id, message.sender_phone,
            message.account_id, reply,
        )

    def _route_to_ai(self, conversation: Conversation, message: WhatsAppMessage) -> Dict[str, Any]:
        """Route message through the AI engine."""
        # Resolve customer
        customer = self._resolve_customer(message.sender_phone)

        # Link customer to conversation if found
        if customer and not conversation.customer_codigo:
            conversation.customer_codigo = customer["codigo"]
            self.conversation_repo.update_customer(conversation.id, customer["codigo"])

        # Build AI context
        context_prefix = ""
        if customer:
            context_prefix = f"[Cliente: {customer['nome']} ({customer['codigo']})]\n"
        if conversation.draft:
            context_prefix += f"[Draft atual: {json.dumps(conversation.draft.to_dict(), ensure_ascii=False)[:500]}]\n"

        # Call AI engine
        ai_result = self.ai_engine.chat(
            message=f"{context_prefix}{message.text}",
            conversation_id=f"wa_{conversation.account_id}_{conversation.customer_phone}",
            permission_level="OPERATOR",
        )

        # Check if AI wants to build an order draft
        intent = ai_result.get("intent")
        entities = ai_result.get("entities", {})

        if intent == "ORDER_CREATE" and ai_result.get("requires_confirmation"):
            # Build draft
            draft = self._build_order_draft(conversation, entities, message)
            if draft:
                conversation.draft = draft
                conversation.transition_to(ConversationState.AWAITING_CONFIRMATION)
                self.conversation_repo.update_draft(conversation.id, draft)
                self.conversation_repo.update_state(conversation.id, ConversationState.AWAITING_CONFIRMATION)

                # Format confirmation message
                reply = self._format_draft_confirmation(draft)
                return self._build_outbound(
                    conversation.id, message.sender_phone,
                    message.account_id, reply,
                )

        # Update conversation state
        if intent and intent != "GENERAL_QUESTION":
            if conversation.state == ConversationState.IDLE:
                conversation.transition_to(ConversationState.BROWSING)
                self.conversation_repo.update_state(conversation.id, ConversationState.BROWSING)

        # Normal AI response
        reply = ai_result.get("message", "Posso ajudar com consultas sobre clientes, pedidos, estoque e financeiro.")
        return self._build_outbound(
            conversation.id, message.sender_phone,
            message.account_id, reply,
        )

    def _build_order_draft(
        self, conversation: Conversation, entities: Dict[str, Any], message: WhatsAppMessage
    ) -> Optional[ConversationDraft]:
        """Build order draft from AI-extracted entities."""
        # Resolve customer
        customer_codigo = conversation.customer_codigo
        customer_name = conversation.customer_phone
        if self.customer_repo and not customer_codigo:
            client = self._resolve_customer(message.sender_phone)
            if client:
                customer_codigo = client["codigo"]
                customer_name = client["nome"]

        if not customer_codigo:
            return None

        # Resolve products and prices
        items = []
        raw_items = entities.get("items", [])
        if not raw_items and entities.get("product_codigo"):
            raw_items = [{"product_codigo": entities["product_codigo"], "quantity": entities.get("quantity", 1)}]

        for raw_item in raw_items:
            product_codigo = raw_item.get("product_codigo", "")
            quantity = raw_item.get("quantity", 1)

            # Look up product price and inventory
            product_info = self._resolve_product(product_codigo)
            if product_info:
                items.append({
                    "product_codigo": product_info["codigo"],
                    "product_nome": product_info["nome"],
                    "quantity": quantity,
                    "unit_price": product_info["preco"],
                    "subtotal": round(product_info["preco"] * quantity, 2),
                })

        if not items:
            return None

        return ConversationDraft(
            customer_codigo=customer_codigo,
            customer_name=customer_name,
            items=items,
        )

    def _resolve_product(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Resolve product by code or name."""
        if not self.product_repo:
            return None
        try:
            # Try exact code first
            product = self.product_repo.buscar_por_codigo(codigo)
            if product:
                return {"codigo": product.codigo, "nome": product.nome, "preco": float(product.preco)}
            # Try search by name
            products = self.product_repo.listar_todos()
            for p in products:
                if codigo.lower() in p.nome.lower():
                    return {"codigo": p.codigo, "nome": p.nome, "preco": float(p.preco)}
        except Exception:
            pass
        return None

    def _format_draft_confirmation(self, draft: ConversationDraft) -> str:
        """Format draft for confirmation request."""
        lines = ["📋 *Resumo do Pedido:*"]
        lines.append(f"Cliente: {draft.customer_name or draft.customer_codigo}")
        lines.append("")
        for i, item in enumerate(draft.items, 1):
            lines.append(
                f"{i}. {item.get('product_nome', item['product_codigo'])} "
                f"× {item['quantity']} = R$ {item['subtotal']:.2f}"
            )
        lines.append("")
        lines.append(f"Subtotal: R$ {draft.subtotal:.2f}")
        if draft.delivery_fee > 0:
            lines.append(f"Entrega: R$ {draft.delivery_fee:.2f}")
        if draft.discount > 0:
            lines.append(f"Desconto: R$ -{draft.discount:.2f}")
        lines.append(f"*Total: R$ {draft.total:.2f}*")
        lines.append("")
        lines.append("Confirma o pedido? (sim/não)")
        return "\n".join(lines)

    def _build_outbound(
        self, conversation_id: int, phone: str, account_id: str, text: str
    ) -> Dict[str, Any]:
        """Build outbound response with message persistence."""
        # Save outgoing message
        outgoing = ConversationMessage(
            conversation_id=conversation_id,
            direction="OUTGOING",
            sender="assistant",
            content=text,
            message_type="TEXT",
        )
        self.message_repo.create(outgoing)

        outbound = WhatsAppOutbound(
            recipient_phone=phone,
            text=text,
            account_id=account_id,
        )
        return {
            "status": "processed",
            "conversation_id": conversation_id,
            "outbound": outbound,
            "outbound_text": text,
            "outbound_to": phone,
            "error": None,
        }


# ── Operator Actions ─────────────────────────────────────

class OperatorGateway:
    """Handles operator actions on conversations (takeover, release, manual reply)."""

    def __init__(
        self,
        conversation_repo: ConversationRepository,
        message_repo: ConversationMessageRepository,
    ):
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo

    def takeover(self, conversation_id: int, operator: str) -> Dict[str, Any]:
        """Operator takes over conversation from AI."""
        conv = self.conversation_repo.find_by_id(conversation_id)
        if not conv:
            return {"success": False, "error": "CONVERSATION_NOT_FOUND"}

        if conv.state == ConversationState.HUMAN_ACTIVE:
            return {"success": False, "error": "ALREADY_HUMAN_ACTIVE"}

        success = self.conversation_repo.takeover(conversation_id, operator)
        if success:
            # Notify customer
            outgoing = ConversationMessage(
                conversation_id=conversation_id,
                direction="OUTGOING",
                sender="system",
                content="Um atendente assumiu a conversa.",
                message_type="TEXT",
            )
            self.message_repo.create(outgoing)
            return {"success": True}
        return {"success": False, "error": "TAKEOVER_FAILED"}

    def release_to_ai(self, conversation_id: int) -> Dict[str, Any]:
        """Release conversation back to AI."""
        conv = self.conversation_repo.find_by_id(conversation_id)
        if not conv:
            return {"success": False, "error": "CONVERSATION_NOT_FOUND"}

        if conv.state != ConversationState.HUMAN_ACTIVE:
            return {"success": False, "error": "NOT_HUMAN_ACTIVE"}

        success = self.conversation_repo.release_to_ai(conversation_id)
        if success:
            outgoing = ConversationMessage(
                conversation_id=conversation_id,
                direction="OUTGOING",
                sender="system",
                content="Conversa devolvida à assistente virtual.",
                message_type="TEXT",
            )
            self.message_repo.create(outgoing)
            return {"success": True}
        return {"success": False, "error": "RELEASE_FAILED"}

    def send_manual_reply(self, conversation_id: int, operator: str, text: str) -> Dict[str, Any]:
        """Operator sends a manual reply."""
        conv = self.conversation_repo.find_by_id(conversation_id)
        if not conv:
            return {"success": False, "error": "CONVERSATION_NOT_FOUND"}

        if conv.state != ConversationState.HUMAN_ACTIVE:
            return {"success": False, "error": "NOT_HUMAN_ACTIVE"}

        outgoing = ConversationMessage(
            conversation_id=conversation_id,
            direction="OUTGOING",
            sender="human",
            content=text,
            message_type="TEXT",
        )
        self.message_repo.create(outgoing)
        return {
            "success": True,
            "outbound": WhatsAppOutbound(
                recipient_phone=conv.customer_phone,
                text=text,
                account_id=conv.account_id,
            ),
        }
