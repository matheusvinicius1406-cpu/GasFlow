"""
AI Engine — FASE 9

Core orchestrator: LLM → Intent → Validation → Tool → Use Case → Domain.
Never allows LLM → Database directly.
"""

import json
import hashlib
import time
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from app.domain.ai.provider import LLMProvider, LLMMessage, LLMRole, LLMResponse
from app.domain.ai.intent import Intent, IntentType, Confidence
from app.domain.ai.tools import ToolRegistry, ToolResult, ToolType
from app.application.ai.prompts import (
    SYSTEM_PROMPT, INTENT_CLASSIFICATION_PROMPT, TOOL_SELECTION_PROMPT,
    RESPONSE_FORMATTING_PROMPT, CONFIRMATION_PROMPT,
)
from app.application.ai.context import ContextBuilder


# Intent → Tool mapping
INTENT_TOOL_MAP = {
    IntentType.CUSTOMER_LOOKUP: "get_customer",
    IntentType.CUSTOMER_SEARCH: "search_customers",
    IntentType.CUSTOMER_SUMMARY: "get_customer_360",
    IntentType.ORDER_LOOKUP: "get_order",
    IntentType.ORDER_STATUS: "get_order",
    IntentType.ORDER_CREATE: "create_order",
    IntentType.PRODUCT_LOOKUP: "search_products",
    IntentType.INVENTORY_LOOKUP: "get_inventory",
    IntentType.INVENTORY_LOW_STOCK: "get_low_stock",
    IntentType.INVENTORY_SUMMARY: "get_inventory_summary",
    IntentType.PAYMENT_LOOKUP: "get_payments",
    IntentType.RECEIVABLE_LOOKUP: "get_receivables",
    IntentType.FINANCIAL_SUMMARY: "get_financial_summary",
    IntentType.SALES_SUMMARY: "get_sales_summary",
    IntentType.GENERAL_QUESTION: None,
}

WRITE_INTENTS = {IntentType.ORDER_CREATE}


class AIEngine:
    """Core AI engine orchestrating LLM, tools, and domain."""

    MAX_TOOL_CALLS = 5
    MAX_RETRIES = 2

    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry,
        conversation_repo=None,
        message_repo=None,
    ):
        self.llm = llm_provider
        self.tools = tool_registry
        self.context_builder = ContextBuilder()
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo
        self._audit_log: List[Dict[str, Any]] = []

    def chat(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        permission_level: str = "OPERATOR",
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process a user message through the AI pipeline."""
        start_time = time.time()
        request_id = request_id or hashlib.md5(
            f"{message}{time.time()}".encode()
        ).hexdigest()[:12]

        # 1. Check LLM availability
        if not self.llm.health_check():
            return {
                "message": "Desculpe, o serviço de IA está temporariamente indisponível.",
                "intent": None,
                "requires_confirmation": False,
                "error": "AI_PROVIDER_UNAVAILABLE",
            }

        # 2. Build conversation context
        conv_messages = self._load_conversation(conversation_id)

        # 3. Classify intent
        intent = self._classify_intent(message, conv_messages)

        # 4. Check permission for write intents
        if intent.type in WRITE_INTENTS:
            if permission_level == "READ_ONLY":
                return {
                    "message": "Você não tem permissão para esta operação.",
                    "intent": intent.type.value,
                    "requires_confirmation": False,
                    "error": "AI_TOOL_NOT_ALLOWED",
                }

        # 5. Execute tool if needed
        tool_result = None
        if intent.tool_name:
            tool_result = self._execute_tool(intent)

        # 6. Build response
        response = self._build_response(message, intent, tool_result, conv_messages)

        # 7. Audit log
        latency_ms = (time.time() - start_time) * 1000
        self._log_audit(request_id, conversation_id, intent, tool_result, latency_ms)

        # 8. Save conversation
        self._save_messages(conversation_id, message, response["message"])

        return response

    def _classify_intent(
        self, message: str, conversation_history: Optional[List[Dict]] = None
    ) -> Intent:
        """Classify user message into an intent using LLM."""
        from app.domain.ai.intent import IntentType

        intent_list = "\n".join(f"- {i.value}" for i in IntentType)
        prompt = INTENT_CLASSIFICATION_PROMPT.format(
            intents=intent_list, message=message
        )

        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content="You are an intent classifier. Respond only with valid JSON."),
            LLMMessage(role=LLMRole.USER, content=prompt),
        ]

        response = self.llm.generate(messages, temperature=0.1, max_tokens=256)

        try:
            parsed = json.loads(response.content)
            intent_type = IntentType(parsed.get("intent", "GENERAL_QUESTION"))
            confidence_val = parsed.get("confidence", 0.5)
            if confidence_val >= 0.8:
                confidence = Confidence.HIGH
            elif confidence_val >= 0.5:
                confidence = Confidence.MEDIUM
            else:
                confidence = Confidence.LOW
            entities = parsed.get("entities", {})
            tool_name = INTENT_TOOL_MAP.get(intent_type)

            return Intent(
                type=intent_type,
                confidence=confidence,
                entities=entities,
                tool_name=tool_name,
                requires_confirmation=(intent_type in WRITE_INTENTS),
                reasoning=parsed.get("reasoning", ""),
            )
        except (json.JSONDecodeError, ValueError, KeyError):
            return Intent(
                type=IntentType.GENERAL_QUESTION,
                confidence=Confidence.LOW,
                reasoning="Failed to classify intent",
            )

    def _execute_tool(self, intent: Intent) -> Optional[ToolResult]:
        """Execute a tool based on intent."""
        if not intent.tool_name:
            return None

        tool = self.tools.get(intent.tool_name)
        if not tool:
            return ToolResult(success=False, error="Tool not found")

        # Validate input
        errors = self.tools.validate_input(intent.tool_name, intent.tool_arguments)
        if errors:
            return ToolResult(success=False, error=f"Validation: {', '.join(errors)}")

        # Execute handler
        if tool.handler:
            try:
                return tool.handler(intent.tool_arguments)
            except Exception as e:
                return ToolResult(success=False, error=str(e))

        return ToolResult(success=False, error="Tool has no handler")

    def _build_response(
        self,
        user_message: str,
        intent: Intent,
        tool_result: Optional[ToolResult],
        conversation_history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Build final response for the user."""
        # If no tool needed and HIGH confidence, generate direct response
        if not tool_result and intent.confidence == Confidence.HIGH:
            context = self.context_builder.build(
                intent.type, intent.entities, conversation_history=conversation_history
            )
            messages = [
                LLMMessage(role=LLMRole.SYSTEM, content=SYSTEM_PROMPT),
                LLMMessage(role=LLMRole.USER, content=f"Contexto:\n{context}\n\nPergunta: {user_message}"),
            ]
            response = self.llm.generate(messages, temperature=0.3)
            return {
                "message": response.content,
                "intent": intent.type.value,
                "requires_confirmation": False,
            }

        # If LOW confidence, ask for clarification
        if intent.confidence == Confidence.LOW:
            return {
                "message": "Não tenho certeza do que você precisa. Pode reformular sua pergunta?",
                "intent": intent.type.value,
                "requires_confirmation": False,
            }

        # If MEDIUM confidence and ambiguous entities
        if intent.ambiguous_entities:
            return {
                "message": f"Encontrei mais de uma opção para: {', '.join(intent.ambiguous_entities)}. Pode especificar?",
                "intent": intent.type.value,
                "requires_confirmation": False,
            }

        # Tool execution result
        if tool_result:
            if tool_result.success:
                # Format response using LLM
                messages = [
                    LLMMessage(role=LLMRole.SYSTEM, content=SYSTEM_PROMPT),
                    LLMMessage(
                        role=LLMRole.USER,
                        content=RESPONSE_FORMATTING_PROMPT.format(
                            user_message=user_message,
                            tool_name=intent.tool_name,
                            tool_result=json.dumps(tool_result.data, default=str, ensure_ascii=False)[:2000],
                        ),
                    ),
                ]
                response = self.llm.generate(messages, temperature=0.3)
                return {
                    "message": response.content,
                    "intent": intent.type.value,
                    "requires_confirmation": False,
                    "tool_used": intent.tool_name,
                    "data": tool_result.data,
                }
            else:
                return {
                    "message": f"Não foi possível completar a operação: {tool_result.error}",
                    "intent": intent.type.value,
                    "requires_confirmation": False,
                    "error": "AI_EXECUTION_FAILED",
                }

        # Write operation requiring confirmation
        if intent.requires_confirmation:
            return {
                "message": f"Entendi que você quer {intent.type.value}. Preciso de confirmação para prosseguir. Deseja continuar?",
                "intent": intent.type.value,
                "requires_confirmation": True,
                "entities": intent.entities,
            }

        # Fallback
        return {
            "message": "Posso ajudar com consultas sobre clientes, pedidos, estoque e financeiro. O que precisa?",
            "intent": intent.type.value,
            "requires_confirmation": False,
        }

    def _load_conversation(self, conversation_id: Optional[str]) -> Optional[List[Dict]]:
        """Load conversation history."""
        if not conversation_id or not self.message_repo:
            return None
        messages = self.message_repo.list_by_conversation(conversation_id, limit=10)
        return [{"role": m.role.value, "content": m.content} for m in messages]

    def _save_messages(self, conversation_id: Optional[str], user_msg: str, assistant_msg: str):
        """Save conversation messages."""
        if not conversation_id or not self.message_repo:
            return
        from app.domain.ai.conversation import Message, MessageRole
        self.message_repo.create(Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=user_msg,
        ))
        self.message_repo.create(Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=assistant_msg,
        ))

    def _log_audit(
        self, request_id: str, conversation_id: Optional[str],
        intent: Intent, tool_result: Optional[ToolResult], latency_ms: float,
    ):
        """Log AI interaction for audit."""
        entry = {
            "request_id": request_id,
            "conversation_id": conversation_id,
            "intent": intent.type.value if intent else None,
            "tool": intent.tool_name if intent else None,
            "confidence": intent.confidence.value if intent else None,
            "success": tool_result.success if tool_result else None,
            "latency_ms": round(latency_ms, 2),
            "model": self.llm.model_name,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._audit_log.append(entry)

    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent audit log entries."""
        return self._audit_log[-limit:]
