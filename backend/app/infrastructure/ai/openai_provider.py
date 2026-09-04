"""OpenAI LLM Provider — implementa LLMProvider (domain) via API OpenAI.

O pacote `openai` é importado de forma lazy: só é necessário quando
AI_PROVIDER=openai está configurado, evitando dependência pesada no
default (mock/ollama). Se faltar a chave ou o pacote, as chamadas
retornam LLMResponse com erro (nunca levantam para o chamador).
"""

import time
from typing import Any, Dict, List

from app.domain.ai.provider import (
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMUsage,
)


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._temperature = temperature

    @property
    def model_name(self) -> str:
        return self._model

    def _client(self):
        try:
            import openai  # noqa: PLC0415 — lazy: dependência opcional
        except ImportError:
            return None
        return openai.AsyncOpenAI(api_key=self._api_key, timeout=self._timeout)

    # ── Interface LLMProvider ─────────────────────────────

    def generate(self, messages: List[LLMMessage], temperature: float = 0.3,
                 max_tokens: int = 2048) -> LLMResponse:
        if not self._api_key:
            return LLMResponse(content="", error="OPENAI_MISSING_API_KEY")
        client = self._client()
        if client is None:
            return LLMResponse(content="", error="OPENAI_NOT_INSTALLED")

        start = time.time()
        try:
            import asyncio  # noqa: PLC0415

            response = asyncio.run(client.chat.completions.create(
                model=self._model,
                messages=[{"role": m.role.value, "content": m.content} for m in messages],
                max_tokens=max_tokens,
                temperature=temperature,
            ))
            latency = (time.time() - start) * 1000
            usage = LLMUsage(
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
                model=self._model,
                latency_ms=latency,
            )
            return LLMResponse(
                content=(response.choices[0].message.content or "") if response.choices else "",
                usage=usage,
            )
        except Exception as exc:  # noqa: BLE001 — qualquer falha vira resposta de erro
            return LLMResponse(content="", error=f"OPENAI_ERROR:{type(exc).__name__}")

    def generate_structured(self, messages: List[LLMMessage], schema: Dict[str, Any],
                            temperature: float = 0.1,
                            max_tokens: int = 1024) -> LLMResponse:
        return self.generate(messages, temperature=min(temperature, 0.2), max_tokens=max_tokens)

    def health_check(self) -> bool:
        return bool(self._api_key) and self._client() is not None
