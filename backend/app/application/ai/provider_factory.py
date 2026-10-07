"""Factory de providers LLM — Item 3 (IA no boot, sem jargão na UI).

Ordem de resolução (decisão da Fase 4.2, cenário B — sem fallback externo):
    1. ai.enabled == false            → NullProvider (IA desligada pelo admin)
    2. health check do Ollama OK      → OllamaProvider
    3. Ollama indisponível            → NullProvider + log (degradação graciosa)

O health check é cacheado por 30s para não bater no Ollama a cada request.
A interface de domínio continua SÍNCRONA (decisão do executor) — nada de
streaming async; o engine e as tools existentes não mudam.
"""

import logging
import time

from app.core.config import settings
from app.domain.ai.provider import LLMProvider
from app.infrastructure.ai.huggingface_provider import HuggingFaceProvider
from app.infrastructure.ai.mock_provider import MockLLMProvider
from app.infrastructure.ai.null_provider import NullProvider
from app.infrastructure.ai.ollama_provider import OllamaProvider
from app.infrastructure.ai.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

# Cache do health check (segundos) — evita GET /api/tags a cada request.
HEALTH_CACHE_TTL_SECONDS = 30.0

_health_cache: dict = {"healthy": False, "at": 0.0}


def _ai_enabled() -> bool:
    """Toggle admin da IA.

    Fonte da verdade é o quadro de configurações (system_settings, chave
    ai.enabled, default True) para que o admin possa desligar a IA em runtime
    sem restart. Se o quadro não estiver disponível (ex.: tabela ainda não
    criada em testes unitários puros), cai no env AI_ENABLED (default on).
    """
    env_flag = getattr(settings, "ai_enabled", True)
    try:
        from app.infrastructure.database.connection import SessionLocal

        session = SessionLocal()
        try:
            from app.application.settings.settings_service import SettingsService

            value = SettingsService(session).get_value("ai.enabled", env_flag)
        finally:
            session.close()
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in ("0", "false", "no", "off")
    except Exception:  # pragma: no cover — fallback silencioso para o env
        logger.debug("provider_factory: ai.enabled via env (settings indisponível)")
    return env_flag


def is_ollama_healthy(force: bool = False) -> bool:
    """Health check do Ollama com cache de 30s (timeout curto, 2s)."""
    now = time.monotonic()
    if not force and (now - _health_cache["at"]) < HEALTH_CACHE_TTL_SECONDS:
        return bool(_health_cache["healthy"])
    healthy = OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout=2.0,
    ).health_check()
    _health_cache["healthy"] = healthy
    _health_cache["at"] = now
    return healthy


def reset_health_cache() -> None:
    """Limpa o cache de health (usado ao mudar settings e nos testes)."""
    _health_cache["healthy"] = False
    _health_cache["at"] = 0.0


def get_llm_provider() -> LLMProvider:
    """Retorna o provider LLM ativo conforme toggle + saúde do Ollama."""
    if not _ai_enabled():
        return NullProvider()

    provider = settings.ai_provider
    if provider == "openai":
        # openai depende de chave configurada — segue caminho direto.
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout=settings.ai_timeout_seconds,
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
        )

    if provider == "hf":
        # Hugging Face (Inference Providers): depende do token HF_TOKEN.
        return HuggingFaceProvider(
            api_token=settings.hf_api_token,
            model=settings.hf_model,
            base_url=settings.hf_base_url,
            timeout=settings.hf_timeout,
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
        )

    if provider == "ollama" and is_ollama_healthy():
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout=settings.ai_timeout_seconds,
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
            think=settings.ollama_think,
        )

    if provider == "mock":
        # Mock é dev/testes apenas — mantém comportamento determinístico.
        return MockLLMProvider()

    # Cenário B: sem fallback externo — degradação graciosa com log.
    logger.warning("ai_provider_unavailable provider=%s — IA desabilitada até o Ollama responder", provider)
    return NullProvider()


def get_renamer_provider() -> LLMProvider | None:
    """Provider da camada de IA do renomeador; ``None`` = IA desligada.

    Independente do ``AI_PROVIDER`` global: o renomeador decide pelo próprio
    env (``RENOMEADOR_IA_PROVIDER``), então dá para ter a IA do app desligada e
    o renomeador rodando (ou vice-versa).

    O default é o Ollama local — nada sai do PC. Só o operador que setar
    ``RENOMEADOR_IA_PROVIDER=hf`` permite que nomes/endereços viajem para a
    Hugging Face; sem token, a chamada é recusada e o renomeador segue só com
    o parser determinístico (degradação graciosa, nunca exceção).
    """
    if not getattr(settings, "renomeador_ia", False):
        return None

    escolha = getattr(settings, "renomeador_ia_provider", "ollama")

    if escolha == "hf":
        if not getattr(settings, "hf_api_token", ""):
            logger.warning("renomeador_ia: RENOMEADOR_IA_PROVIDER=hf sem HF_TOKEN — IA ignorada")
            return None
        return HuggingFaceProvider(
            api_token=settings.hf_api_token,
            model=settings.hf_model,
            base_url=settings.hf_base_url,
            timeout=settings.hf_timeout,
            max_tokens=900,
            temperature=0.1,
        )

    provider = OllamaProvider(
        base_url=settings.ollama_base_url,
        model=getattr(settings, "renomeador_ia_model", "qwen3:1.7b"),
        timeout=getattr(settings, "renomeador_ia_timeout", 60),
        max_tokens=900,
        temperature=0.1,
        think=False,
    )
    if not provider.health_check():
        logger.warning("renomeador_ia: Ollama indisponível — renomeando apenas com o parser determinístico")
        return None
    return provider
