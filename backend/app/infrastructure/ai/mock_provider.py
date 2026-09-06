"""
Mock LLM Provider — FASE 9

Deterministic mock for testing without external API.
"""

import json
from typing import List, Dict, Any, Optional
from app.domain.ai.provider import LLMProvider, LLMMessage, LLMResponse, LLMUsage


class MockLLMProvider(LLMProvider):
    """Deterministic mock LLM provider for testing."""

    def __init__(self, responses: Optional[Dict[str, str]] = None):
        self._responses = responses or {}
        self._call_count = 0
        self._available = True

    @property
    def model_name(self) -> str:
        return "mock-model-v1"

    def generate(self, messages: List[LLMMessage], temperature: float = 0.3, max_tokens: int = 2048) -> LLMResponse:
        self._call_count += 1
        if not self._available:
            return LLMResponse(content="", error="AI_PROVIDER_UNAVAILABLE")

        # Check for pre-configured responses
        last_msg = messages[-1].content if messages else ""
        for key, response in self._responses.items():
            if key.lower() in last_msg.lower():
                return LLMResponse(
                    content=response,
                    usage=LLMUsage(input_tokens=100, output_tokens=50, model=self.model_name, latency_ms=10),
                )

        # Default responses based on content
        if "classify" in last_msg.lower() or "intent" in last_msg.lower():
            return self._default_intent_classification(last_msg)
        elif "tool" in last_msg.lower() and "select" in last_msg.lower():
            return self._default_tool_selection(last_msg)
        elif "format" in last_msg.lower() or "respon" in last_msg.lower():
            return self._default_format_response(last_msg)

        return LLMResponse(
            content="Desculpe, não consegui processar sua mensagem.",
            usage=LLMUsage(input_tokens=50, output_tokens=20, model=self.model_name, latency_ms=10),
        )

    def generate_structured(
        self, messages: List[LLMMessage], schema: Dict[str, Any], temperature: float = 0.1, max_tokens: int = 1024
    ) -> LLMResponse:
        return self.generate(messages, temperature, max_tokens)

    def health_check(self) -> bool:
        return self._available

    def set_unavailable(self):
        self._available = False

    def set_available(self):
        self._available = True

    def _default_intent_classification(self, text: str) -> LLMResponse:
        """Classify intent from text."""
        # Extract the actual user message from the formatted prompt
        user_msg = text
        if "User message:" in text:
            user_msg = text.split("User message:")[-1].strip().split("\n")[0]
        elif "message:" in text:
            user_msg = text.split("message:")[-1].strip().split("\n")[0]
        text_lower = user_msg.lower()
        if any(w in text_lower for w in ["criar pedido", "cria pedido", "crie um pedido", "novo pedido"]):
            intent = "ORDER_CREATE"
        elif any(w in text_lower for w in ["quanto", "estoque", "temos de", "stock"]):
            intent = "INVENTORY_LOOKUP"
        elif any(w in text_lower for w in ["quem é", "cliente", "customer"]):
            intent = "CUSTOMER_LOOKUP"
        elif any(w in text_lower for w in ["pedido", "order"]):
            intent = "ORDER_LOOKUP"
        elif any(w in text_lower for w in ["pagamento", "pagar", "receber", "financeiro"]):
            intent = "FINANCIAL_SUMMARY"
        else:
            intent = "GENERAL_QUESTION"

        return LLMResponse(
            content=json.dumps(
                {
                    "intent": intent,
                    "confidence": 0.9,
                    "entities": {},
                    "reasoning": f"Matched pattern for {intent}",
                }
            ),
            usage=LLMUsage(input_tokens=100, output_tokens=50, model=self.model_name),
        )

    def _default_tool_selection(self, text: str) -> LLMResponse:
        return LLMResponse(
            content=json.dumps({"tool": "get_customer", "arguments": {}, "requires_confirmation": False}),
            usage=LLMUsage(input_tokens=100, output_tokens=30, model=self.model_name),
        )

    def _default_format_response(self, text: str) -> LLMResponse:
        # Try to extract data from the text and format it
        return LLMResponse(
            content="Aqui estão os dados encontrados.",
            usage=LLMUsage(input_tokens=200, output_tokens=50, model=self.model_name),
        )
