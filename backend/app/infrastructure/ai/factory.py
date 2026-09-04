"""Factory de providers LLM — resolve o provider ativo pelas settings.

A regra de negócio NUNCA escolhe provider: ela recebe um LLMProvider daqui.
Default é mock (dev/testes); produção define AI_PROVIDER=ollama|openai.
"""

from app.core.config import settings
from app.domain.ai.provider import LLMProvider
from app.infrastructure.ai.mock_provider import MockLLMProvider
from app.infrastructure.ai.ollama_provider import OllamaProvider
from app.infrastructure.ai.openai_provider import OpenAIProvider


def get_llm_provider() -> LLMProvider:
    """Retorna o provider LLM ativo conforme settings.ai_provider."""
    provider = settings.ai_provider
    if provider == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout=settings.ai_timeout_seconds,
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
        )
    if provider == "openai":
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout=settings.ai_timeout_seconds,
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
        )
    # Qualquer outro valor (incluindo "mock" e valores desconhecidos) cai
    # no mock determinístico — comportamento seguro para dev/testes.
    return MockLLMProvider()
