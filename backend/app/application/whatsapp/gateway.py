"""
Message Gateway — FASE 10.X (HARDENED)

Processes incoming WhatsApp messages with full production maturity:
1. Validate schema
2. Normalize phone
3. Deduplication
4. Rate limiting
5. Resolve customer
6. Check ownership
7. Route to AI or human
8. Stock/price recheck before confirmation
9. Build response
10. Observability metrics

Architecture: WhatsApp → Message Gateway → Conversation → AI Core → Tools → Use Cases → Domain
"""

import json
import time
import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from collections import defaultdict
import threading

from app.domain.whatsapp.message import WhatsAppMessage, WhatsAppOutbound, MessageType
from app.domain.whatsapp.conversation import (
    Conversation,
    ConversationState,
    ConversationDraft,
    ConversationMessage,
)
from app.domain.whatsapp.repository import ConversationRepository, ConversationMessageRepository
from app.application.ai.engine import AIEngine


# ── Anti-loop ────────────────────────────────────────────
LOOP_MARKER = "[AI]"

# ── Confirmation patterns ────────────────────────────────
CONFIRMATION_POSITIVE = re.compile(
    r"^\s*(sim|s[íi]|confirmo?|pode mandar|fechar pedido|pode fechar|"
    r"fecho|bora|beleza|ok|pode|aprovo?|confirmar|manda|pode ser|isso)\s*[!?.]*\s*$",
    re.IGNORECASE,
)
CONFIRMATION_NEGATIVE = re.compile(
    r"^\s*(n[ãa]o|n[ãa]o quero|cancela|deixa pra l[áa]|desisto|esquece|não|nah|nope)\s*[!?.]*\s*$",
    re.IGNORECASE,
)
AMBIGUOUS_CONFIRMATION = re.compile(
    r"^\s*(talvez|acho que sim|acho que n[ãa]o|depois|provavelmente|n[ãa]o sei|"
    r"vou ver|depois eu|me pergunto|ser[áa] que)\s*[!?.]*\s*$",
    re.IGNORECASE,
)
RESET_PATTERNS = re.compile(
    r"^\s*(come[cç]ar de novo|novo pedido|resetar|limpar|recome[cç]ar)\s*[!?.]*\s*$",
    re.IGNORECASE,
)
HUMAN_REQUEST = re.compile(
    r"(falar com atendente|falar com humano|humano|atendente|pessoa real|"
    r"suporte humano|falar com algu[eé]m|quero atendente)",
    re.IGNORECASE,
)

# ── Draft expiration ─────────────────────────────────────
DRAFT_TTL_MINUTES = 30

# ── Rate limiting ────────────────────────────────────────
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_MESSAGES = 30  # per window per phone


class MessageGateway:
    """
    Central message processing gateway (HARDENED).
    Orchestrates: validation → normalization → dedup → rate limit → customer resolution
    → ownership check → AI routing → stock/price recheck → response building.
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

        # ── Observability metrics ─────────────────────────
        self._metrics = {
            "messages_received": 0,
            "messages_processed": 0,
            "duplicate_messages": 0,
            "ai_calls": 0,
            "ai_failures": 0,
            "orders_created": 0,
            "human_handoffs": 0,
            "rate_limited": 0,
            "drafts_expired": 0,
            "stock_rechecks_failed": 0,
            "outbound_sent": 0,
            "outbound_failed": 0,
        }
        self._metrics_lock = threading.Lock()

        # ── Rate limiting state ───────────────────────────
        self._rate_buckets: Dict[str, List[float]] = defaultdict(list)
        self._rate_lock = threading.Lock()

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics snapshot."""
        with self._metrics_lock:
            return dict(self._metrics)

    def process_incoming(
        self,
        raw_message: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Process an incoming WhatsApp message through the full hardened pipeline.
        """
        start_time = time.time()

        # 1. Parse and validate
        message = self._parse_message(raw_message)
        if not message:
            return {"status": "error", "error": "MESSAGE_INVALID", "outbound": None}

        # 2. Anti-loop: skip messages from ourselves
        if message.from_me:
            self._inc_metric("messages_received")
            return {"status": "skipped", "error": "FROM_ME", "outbound": None}

        # 3. Skip non-text messages for now
        if message.message_type != MessageType.TEXT:
            self._inc_metric("messages_received")
            return self._handle_media_message(message)

        # 4. Skip empty messages
        if not message.text or not message.text.strip():
            self._inc_metric("messages_received")
            return {"status": "skipped", "error": "EMPTY_MESSAGE", "outbound": None}

        self._inc_metric("messages_received")

        # 5. Rate limiting
        if self._is_rate_limited(message.sender_phone):
            self._inc_metric("rate_limited")
            return {"status": "skipped", "error": "RATE_LIMITED", "outbound": None}

        # 6. Find or create conversation
        conversation = self._get_or_create_conversation(message)

        # 7. Idempotency check
        if self.conversation_repo.find_duplicate_message(message.provider_message_id):
            self._inc_metric("duplicate_messages")
            return {"status": "skipped", "error": "DUPLICATE_MESSAGE", "conversation_id": conversation.id}

        # 8. Save incoming message
        incoming_msg = ConversationMessage(
            conversation_id=conversation.id,
            direction="INCOMING",
            sender="customer",
            content=message.text,
            message_type=message.message_type.value,
            metadata={"provider_message_id": message.provider_message_id},
        )
        self.message_repo.create(incoming_msg)

        # 9. Check if human operator is active
        if conversation.state == ConversationState.HUMAN_ACTIVE:
            return {"status": "human_active", "conversation_id": conversation.id, "outbound": None}

        # 10. Check for human handoff request
        if HUMAN_REQUEST.search(message.text):
            self._inc_metric("human_handoffs")
            return self._request_human_handoff(conversation, message)

        # 11. Expire stale drafts
        self._expire_draft(conversation)

        # 12. Check for draft confirmation
        if conversation.draft and conversation.state == ConversationState.AWAITING_CONFIRMATION:
            return self._handle_confirmation(conversation, message)

        # 13. Check for draft cancellation
        if conversation.draft and CONFIRMATION_NEGATIVE.search(message.text):
            return self._cancel_draft(conversation, message)

        # 14. Check for reset
        if RESET_PATTERNS.search(message.text):
            return self._reset_conversation(conversation, message)

        # 15. Route through AI engine
        result = self._route_to_ai(conversation, message)

        self._inc_metric("messages_processed")
        latency_ms = (time.time() - start_time) * 1000
        return result

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

            # Validate account_id
            if account_id not in ("primary", "secondary"):
                account_id = "primary"

            msg_type = MessageType.TEXT
            for mt in MessageType:
                if mt.value == message_type_str.upper():
                    msg_type = mt
                    break

            return WhatsAppMessage(
                provider_message_id=provider_message_id,
                account_id=account_id,
                sender_phone=sender_phone,
                text=text.strip()[:4096],  # Truncate oversized messages
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

    def _is_rate_limited(self, phone: str) -> bool:
        """Check if phone has exceeded rate limit."""
        now = time.time()
        with self._rate_lock:
            bucket = self._rate_buckets[phone]
            # Remove entries outside the window
            cutoff = now - RATE_LIMIT_WINDOW_SECONDS
            bucket[:] = [t for t in bucket if t > cutoff]
            if len(bucket) >= RATE_LIMIT_MAX_MESSAGES:
                return True
            bucket.append(now)
            return False

    def _get_or_create_conversation(self, message: WhatsAppMessage) -> Conversation:
        """Find existing conversation or create new one."""
        existing = self.conversation_repo.find_by_phone_and_account(message.sender_phone, message.account_id)
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
            "outbound_text": reply,
            "outbound_to": message.sender_phone,
            "error": None,
        }

    def _handle_confirmation(self, conversation: Conversation, message: WhatsAppMessage) -> Dict[str, Any]:
        """Handle order draft confirmation with stock/price recheck."""
        # Ambiguous → ask for clarification
        if AMBIGUOUS_CONFIRMATION.search(message.text):
            reply = "Preciso de uma confirmação clara. Digite 'sim' para confirmar ou 'não' para cancelar."
            return self._build_outbound(
                conversation.id,
                message.sender_phone,
                message.account_id,
                reply,
            )

        if CONFIRMATION_POSITIVE.search(message.text):
            # Stock/price recheck before creating order
            recheck = self._recheck_draft(conversation)
            if not recheck["ok"]:
                return self._build_outbound(
                    conversation.id,
                    conversation.customer_phone,
                    conversation.account_id,
                    recheck["message"],
                )
            # Execute order creation
            result = self._execute_order_creation(conversation)
            self._inc_metric("messages_processed")
            if result["success"]:
                self._inc_metric("orders_created")
            return self._build_outbound(
                conversation.id,
                conversation.customer_phone,
                conversation.account_id,
                result["message"],
            )
        elif CONFIRMATION_NEGATIVE.search(message.text):
            return self._cancel_draft(conversation, message)
        else:
            reply = "Não entendi se você confirma ou cancela. Pode digitar 'sim' ou 'não'?"
            return self._build_outbound(
                conversation.id,
                message.sender_phone,
                message.account_id,
                reply,
            )

    def _recheck_draft(self, conversation: Conversation) -> Dict[str, Any]:
        """
        Recheck stock availability and prices before order confirmation.
        If anything changed since draft was created, inform the customer.
        """
        draft = conversation.draft
        if not draft or not draft.items:
            return {"ok": False, "message": "Draft inválido."}

        # Recheck each item
        updated_items = []
        for item in draft.items:
            product_codigo = item.get("product_codigo")
            quantity = item.get("quantity", 1)

            # Recheck stock
            if self.inventory_repo:
                try:
                    inv = self.inventory_repo.get_by_product(product_codigo)
                    if inv and inv.quantity < quantity:
                        return {
                            "ok": False,
                            "message": (
                                f"Desculpe, o produto {item.get('product_nome', product_codigo)} "
                                f"só tem {inv.quantity} unidades em estoque. "
                                f"Não posso confirmar o pedido com {quantity}."
                            ),
                        }
                except Exception:
                    pass  # If inventory check fails, proceed (order UseCase will catch)

            # Recheck price
            product_info = self._resolve_product(product_codigo)
            if product_info:
                old_price = item.get("unit_price", 0)
                new_price = product_info["preco"]
                if old_price != new_price:
                    # Update draft with new price
                    item["unit_price"] = new_price
                    item["subtotal"] = round(new_price * quantity, 2)
                    self.conversation_repo.update_draft(conversation.id, draft)

        return {"ok": True, "message": ""}

    def _execute_order_creation(self, conversation: Conversation) -> Dict[str, Any]:
        """Execute order creation through AI tool → UseCase."""
        draft = conversation.draft
        if not draft or not draft.customer_codigo:
            return {"success": False, "message": "Draft inválido."}

        # Build items for CreateOrderUseCase
        items = []
        for item in draft.items:
            items.append(
                {
                    "product_codigo": item.get("product_codigo"),
                    "quantity": item.get("quantity"),
                }
            )

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
            self._inc_metric("ai_failures")
            return {"success": False, "message": f"Erro interno: {str(e)}"}

    def _cancel_draft(self, conversation: Conversation, message: WhatsAppMessage) -> Dict[str, Any]:
        """Cancel current order draft."""
        conversation.draft = None
        self.conversation_repo.update_draft(conversation.id, None)
        conversation.transition_to(ConversationState.BROWSING)
        self.conversation_repo.update_state(conversation.id, ConversationState.BROWSING)
        reply = "Pedido cancelado. Posso ajudar com mais alguma coisa?"
        return self._build_outbound(
            conversation.id,
            message.sender_phone,
            message.account_id,
            reply,
        )

    def _reset_conversation(self, conversation: Conversation, message: WhatsAppMessage) -> Dict[str, Any]:
        """Reset conversation state."""
        conversation.draft = None
        self.conversation_repo.update_draft(conversation.id, None)
        conversation.transition_to(ConversationState.IDLE)
        self.conversation_repo.update_state(conversation.id, ConversationState.IDLE)
        reply = "OK, recomeçamos. O que você precisa?"
        return self._build_outbound(
            conversation.id,
            message.sender_phone,
            message.account_id,
            reply,
        )

    def _expire_draft(self, conversation: Conversation) -> None:
        """Expire draft if too old."""
        if conversation.draft and conversation.updated_at:
            age = datetime.utcnow() - conversation.updated_at
            if age > timedelta(minutes=DRAFT_TTL_MINUTES):
                conversation.draft = None
                self.conversation_repo.update_draft(conversation.id, None)
                # Transition back to BROWSING if we were in confirmation
                if conversation.state == ConversationState.AWAITING_CONFIRMATION:
                    conversation.transition_to(ConversationState.BROWSING)
                    self.conversation_repo.update_state(conversation.id, ConversationState.BROWSING)
                self._inc_metric("drafts_expired")

    def _route_to_ai(self, conversation: Conversation, message: WhatsAppMessage) -> Dict[str, Any]:
        """Route message through the AI engine."""
        # Resolve customer
        customer = self._resolve_customer(message.sender_phone)

        # Link customer to conversation if found
        if customer and not conversation.customer_codigo:
            conversation.customer_codigo = customer["codigo"]
            self.conversation_repo.update_customer(conversation.id, customer["codigo"])

        # Build AI context (truncated to prevent context overflow)
        context_prefix = ""
        if customer:
            context_prefix = f"[Cliente: {customer['nome']} ({customer['codigo']})]\n"
        if conversation.draft:
            draft_json = json.dumps(conversation.draft.to_dict(), ensure_ascii=False)[:500]
            context_prefix += f"[Draft atual: {draft_json}]\n"

        # Call AI engine
        self._inc_metric("ai_calls")
        try:
            ai_result = self.ai_engine.chat(
                message=f"{context_prefix}{message.text}",
                conversation_id=f"wa_{conversation.account_id}_{conversation.customer_phone}",
                permission_level="OPERATOR",
            )
        except Exception:
            self._inc_metric("ai_failures")
            return self._build_outbound(
                conversation.id,
                message.sender_phone,
                message.account_id,
                "Desculpe, tive um problema ao processar sua mensagem. Pode tentar novamente?",
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
                    conversation.id,
                    message.sender_phone,
                    conversation.account_id,
                    reply,
                )

        # Update conversation state
        if intent and intent != "GENERAL_QUESTION":
            if conversation.state == ConversationState.IDLE:
                conversation.transition_to(ConversationState.BROWSING)
                self.conversation_repo.update_state(conversation.id, ConversationState.BROWSING)

        # Normal AI response
        reply = ai_result.get("message", "Posso ajudar com consultas sobre clientes, pedidos, estoque e financeiro.")
        return self._build_outbound(
            conversation.id,
            message.sender_phone,
            conversation.account_id,
            reply,
        )

    def _build_order_draft(
        self, conversation: Conversation, entities: Dict[str, Any], message: WhatsAppMessage
    ) -> Optional[ConversationDraft]:
        """Build order draft from AI-extracted entities with stock validation."""
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
                items.append(
                    {
                        "product_codigo": product_info["codigo"],
                        "product_nome": product_info["nome"],
                        "quantity": quantity,
                        "unit_price": product_info["preco"],
                        "subtotal": round(product_info["preco"] * quantity, 2),
                    }
                )

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

    def _build_outbound(self, conversation_id: int, phone: str, account_id: str, text: str) -> Dict[str, Any]:
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

    def _inc_metric(self, key: str) -> None:
        """Thread-safe metric increment."""
        with self._metrics_lock:
            if key in self._metrics:
                self._metrics[key] += 1


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

        if conv.state == ConversationState.CLOSED:
            return {"success": False, "error": "CONVERSATION_CLOSED"}

        success = self.conversation_repo.takeover(conversation_id, operator)
        if success:
            # Notify customer
            outgoing = ConversationMessage(
                conversation_id=conversation_id,
                direction="OUTGOING",
                sender="system",
                content="Um atendente assumiu a conversa. Como posso ajudar?",
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
                content="Conversa devolvida à assistente virtual. Como posso ajudar?",
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
