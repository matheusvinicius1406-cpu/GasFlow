"""NullProvider — LLMProvider no-op quando a IA está desligada pelo admin.

Decisão da Fase 4.2 (cenário B): NÃO existe provider externo de fallback —
a degradação graciosa é o próprio NullProvider + mensagem controlada na UI.
Nunca lança: devolve LLMResponse.error="AI_DISABLED" para o chamador mapear.
"""

from typing import Dict, List

from app.domain.ai.provider import LLMMessage, LLMProvider, LLMResponse


class NullProvider(LLMProvider):
    """Provider nulo — IA desativada (ai.enabled == false) ou indisponível."""

    @property
    def model_name(self) -> str:
        return "none"

    def generate(self, messages: List[LLMMessage], temperature: float = 0.3, max_tokens: int = 2048) -> LLMResponse:
        _ = messages, temperature, max_tokens  # interface — sem uso
        return LLMResponse(content="", error="AI_DISABLED")

    def generate_structured(
        self, messages: List[LLMMessage], schema: Dict[str, object], temperature: float = 0.1, max_tokens: int = 1024
    ) -> LLMResponse:
        _ = messages, schema, temperature, max_tokens  # interface — sem uso
        return LLMResponse(content="", error="AI_DISABLED")

    def health_check(self) -> bool:
        return False
