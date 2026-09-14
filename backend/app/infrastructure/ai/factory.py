"""Factory de providers LLM — módulo legado.

A implementação real migrou para app/application/ai/provider_factory.py
(Item 3: toggle ai.enabled, health cache 30s, NullProvider). Este módulo
permanece apenas como re-export para não quebrar os importers existentes
(ai.py, whatsapp_gateway.py, contacts/service.py, testes).
"""

from app.application.ai.provider_factory import (  # noqa: F401
    get_llm_provider,
    is_ollama_healthy,
    reset_health_cache,
)
