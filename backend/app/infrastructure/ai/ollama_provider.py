"""Ollama LLM Provider — implementa LLMProvider (domain) via API local do Ollama.

Sem regras de negócio aqui: apenas transporte HTTP + mapeamento de erros.
Configuração (base_url/model/timeouts) vem de fora (settings/factory).
"""

import time
from typing import Any, Dict, List

import httpx

from app.domain.ai.provider import (
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMUsage,
)


class OllamaProvider(LLMProvider):
    """Provider para servidores Ollama (/api/chat, /api/tags)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        timeout: float = 60.0,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._temperature = temperature

    @property
    def model_name(self) -> str:
        return self._model

    # ── Internals ─────────────────────────────────────────

    def _payload(self, messages: List[LLMMessage], temperature: float,
                 max_tokens: int) -> Dict[str, Any]:
        return {
            "model": self._model,
            "messages": [{"role": m.role.value, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

    def _to_response(self, data: Dict[str, Any], latency_ms: float) -> LLMResponse:
        usage = LLMUsage(
            input_tokens=int(data.get("prompt_eval_count") or 0),
            output_tokens=int(data.get("eval_count") or 0),
            model=self._model,
            latency_ms=latency_ms,
        )
        return LLMResponse(
            content=data.get("message", {}).get("content", ""),
            usage=usage,
            finish_reason=data.get("done_reason") or "stop",
        )

    # ── Interface LLMProvider ─────────────────────────────

    def generate(self, messages: List[LLMMessage], temperature: float = 0.3,
                 max_tokens: int = 2048) -> LLMResponse:
        start = time.time()
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}/api/chat",
                    json=self._payload(messages, temperature, max_tokens),
                )
                response.raise_for_status()
                latency = (time.time() - start) * 1000
                return self._to_response(response.json(), latency)
        except httpx.HTTPStatusError as exc:
            return LLMResponse(
                content="", error=f"LLM_HTTP_ERROR:{exc.response.status_code}"
            )
        except (httpx.HTTPError, OSError) as exc:
            return LLMResponse(content="", error=f"LLM_UNAVAILABLE:{type(exc).__name__}")

    def generate_structured(self, messages: List[LLMMessage], schema: Dict[str, Any],
                            temperature: float = 0.1,
                            max_tokens: int = 1024) -> LLMResponse:
        # O Ollama não tem schema-enforcement nativo na API /chat; o JSON de
        # schema é injetado no prompt pelo chamador (AIEngine). Aqui apenas
        # pedimos resposta mais determinística.
        return self.generate(messages, temperature=min(temperature, 0.2), max_tokens=max_tokens)

    def health_check(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self._base_url}/api/tags")
                return response.status_code == 200
        except (httpx.HTTPError, OSError):
            return False
