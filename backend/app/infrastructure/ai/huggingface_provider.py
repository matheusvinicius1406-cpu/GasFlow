"""Hugging Face LLM Provider — implementa LLMProvider via Inference Providers.

Endpoint compatível com OpenAI (``/chat/completions`` do router da HF), usado
com o token do env ``HF_TOKEN``. Sem dependência nova: httpx já é requisito do
backend.

Decisões de segurança:
- O token só vive nesta instância; nunca entra em log, mensagem de erro ou
  repr (``__repr__`` mascarado) — o histórico de erro devolve apenas o código
  HTTP, nunca cabeçalhos.
- É o provider OPT-IN: o caminho padrão do renomeador é o Ollama local, para
  que dados de cliente não saiam do PC.
- Sem chave → erro estruturado (nunca exceção), para o chamador cair no
  caminho determinístico.
"""

import time
from typing import Any, Dict, List

import httpx

from app.domain.ai.provider import LLMMessage, LLMProvider, LLMResponse, LLMUsage


class HuggingFaceProvider(LLMProvider):
    def __init__(
        self,
        api_token: str = "",
        model: str = "Qwen/Qwen3-8B",
        base_url: str = "https://router.huggingface.co/v1",
        timeout: float = 30.0,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> None:
        self._token = api_token
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._temperature = temperature

    def __repr__(self) -> str:  # nunca vaza o token em logs de depuração
        return f"HuggingFaceProvider(model={self._model!r}, token=<oculto>)"

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, messages: List[LLMMessage], temperature: float = 0.3, max_tokens: int = 2048) -> LLMResponse:
        if not self._token:
            return LLMResponse(content="", error="HF_MISSING_TOKEN")
        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role.value, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self._token}"}
        start = time.time()
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(f"{self._base_url}/chat/completions", json=payload, headers=headers)
                # Nunca propaga o corpo/cabeçalhos de erro: podem ecoar a URL
                # ou detalhes internos. Só o status.
                if response.status_code >= 400:
                    return LLMResponse(content="", error=f"HF_HTTP_ERROR:{response.status_code}")
                data = response.json()
        except httpx.HTTPError as exc:
            return LLMResponse(content="", error=f"HF_UNAVAILABLE:{type(exc).__name__}")
        except (ValueError, TypeError):
            return LLMResponse(content="", error="HF_BAD_RESPONSE")

        latency = (time.time() - start) * 1000
        usage_raw = data.get("usage") or {}
        usage = LLMUsage(
            input_tokens=int(usage_raw.get("prompt_tokens") or 0),
            output_tokens=int(usage_raw.get("completion_tokens") or 0),
            model=self._model,
            latency_ms=latency,
        )
        choices = data.get("choices") or []
        return LLMResponse(
            content=(choices[0].get("message", {}) or {}).get("content", "") if choices else "",
            usage=usage,
        )

    def generate_structured(
        self, messages: List[LLMMessage], schema: Dict[str, Any], temperature: float = 0.1, max_tokens: int = 1024
    ) -> LLMResponse:
        return self.generate(messages, temperature=min(temperature, 0.2), max_tokens=max_tokens)

    def health_check(self) -> bool:
        return bool(self._token)
