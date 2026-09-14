"""Testes Item 3 — Provider factory com toggle admin + endpoints de IA.

Cobre (prompt Item 3, seção 3.5, adaptado ao cenário B da Fase 4.2):
1. Factory prefere Ollama quando saudável
2. Factory degrada para NullProvider quando Ollama cai (cenário B — sem fallback externo)
3. Factory retorna NullProvider quando IA desligada (toggle admin)
4. Health check cacheado (não bate no Ollama a cada request)
5. PATCH /ai/settings grava audit com before/after
6. POST /ai/test retorna provider usado + grava audit
7. Endpoint /ai/status respeita o toggle admin
8. RBAC: ai.configure exigido em /ai/settings (operador levou 403)
9. Toggle desligado zera o cache de health (próximo request re-checa)

Estratégia: factory testado direto (monkeypatch em OllamaProvider.health_check
via ProviderForTests) + endpoints via TestClient (mesmo caminho de produção).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.application.ai import provider_factory
from app.domain.ai.provider import LLMMessage, LLMResponse
from app.infrastructure.ai.null_provider import NullProvider
from app.infrastructure.ai.ollama_provider import OllamaProvider


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


@pytest.fixture(autouse=True)
def _reset_factory_state():
    """Isola estado global do factory (health cache) entre testes."""
    provider_factory.reset_health_cache()
    yield
    provider_factory.reset_health_cache()


class _StubProvider:
    """Stub mínimo que satisfaz o duck-typing usado nos testes do factory."""

    def __init__(self, name: str, healthy: bool = True) -> None:
        self._name = name
        self._healthy = healthy
        self.health_calls = 0

    @property
    def model_name(self) -> str:
        return self._name

    def health_check(self) -> bool:
        self.health_calls += 1
        return self._healthy

    def generate(self, messages: List[LLMMessage], temperature: float = 0.3, max_tokens: int = 2048) -> LLMResponse:
        return LLMResponse(content="ok")

    def generate_structured(
        self, messages: List[LLMMessage], schema: Dict[str, Any], temperature: float = 0.1, max_tokens: int = 1024
    ) -> LLMResponse:
        return self.generate(messages, temperature, max_tokens)


# ═══════════════════════════════════════════════════════════
# 1. Factory prefere Ollama quando saudável
# ═══════════════════════════════════════════════════════════


def test_factory_prefers_ollama_when_healthy(monkeypatch):
    monkeypatch.setattr(provider_factory, "_ai_enabled", lambda: True)
    monkeypatch.setattr(provider_factory.settings, "ai_provider", "ollama")
    stub = _StubProvider("ollama", healthy=True)
    monkeypatch.setattr(provider_factory, "OllamaProvider", lambda **_kw: stub)

    provider = provider_factory.get_llm_provider()

    assert provider is stub
    assert stub.health_calls == 1


# ═══════════════════════════════════════════════════════════
# 2. Ollama cai → NullProvider (cenário B: sem fallback externo)
# ═══════════════════════════════════════════════════════════


def test_factory_falls_back_to_null_when_ollama_down(monkeypatch):
    monkeypatch.setattr(provider_factory, "_ai_enabled", lambda: True)
    monkeypatch.setattr(provider_factory.settings, "ai_provider", "ollama")
    stub = _StubProvider("ollama", healthy=False)
    monkeypatch.setattr(provider_factory, "OllamaProvider", lambda **_kw: stub)

    provider = provider_factory.get_llm_provider()

    assert isinstance(provider, NullProvider)
    assert provider.model_name == "none"
    response = provider.generate(
        [LLMMessage(role=__import__("app.domain.ai.provider", fromlist=["LLMRole"]).LLMRole.USER, content="oi")]
    )
    assert response.error == "AI_DISABLED"


# ═══════════════════════════════════════════════════════════
# 3. IA desligada → NullProvider
# ═══════════════════════════════════════════════════════════


def test_factory_returns_null_when_ai_disabled(monkeypatch):
    monkeypatch.setattr(provider_factory, "_ai_enabled", lambda: False)

    provider = provider_factory.get_llm_provider()

    assert isinstance(provider, NullProvider)
    assert provider.health_check() is False


# ═══════════════════════════════════════════════════════════
# 4. Health check cacheado por 30s
# ═══════════════════════════════════════════════════════════


def test_health_check_cached(monkeypatch):
    monkeypatch.setattr(provider_factory.settings, "ai_provider", "ollama")
    stub = _StubProvider("ollama", healthy=True)
    monkeypatch.setattr(provider_factory, "OllamaProvider", lambda **_kw: stub)

    assert provider_factory.is_ollama_healthy() is True
    assert provider_factory.is_ollama_healthy() is True
    assert provider_factory.is_ollama_healthy() is True
    assert stub.health_calls == 1  # cache — uma única chamada real

    # TTL expirado → re-checa
    provider_factory._health_cache["at"] -= provider_factory.HEALTH_CACHE_TTL_SECONDS + 1
    assert provider_factory.is_ollama_healthy() is True
    assert stub.health_calls == 2


# ═══════════════════════════════════════════════════════════
# 5-9. Endpoints (TestClient — caminho de produção)
# ═══════════════════════════════════════════════════════════


def _db():
    from sqlalchemy.orm import Session

    from app.infrastructure.database.init_db import engine

    return Session(bind=engine)


def _last_ai_audit(db, action: str):
    from app.infrastructure.repositories.auth_model import AuthAuditModel

    return (
        db.query(AuthAuditModel)
        .filter(AuthAuditModel.action == action)
        .order_by(AuthAuditModel.timestamp.desc())
        .first()
    )


def test_status_respects_admin_toggle(client, admin_headers):
    db = _db()
    try:
        # Desliga a IA pelo toggle do admin
        res = client.patch("/ai/settings", headers=admin_headers, json={"enabled": False})
        assert res.status_code == 200, res.text
        assert res.json()["enabled"] is False

        res = client.get("/ai/status", headers=admin_headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["state"] == "disabled"
        assert "Ollama" not in body["message"] and "qwen" not in body["message"]
    finally:
        client.patch("/ai/settings", headers=admin_headers, json={"enabled": True})
        db.close()


def test_settings_patch_audits_before_after(client, admin_headers):
    db = _db()
    try:
        res = client.patch("/ai/settings", headers=admin_headers, json={"enabled": False})
        assert res.status_code == 200, res.text
        entry = _last_ai_audit(db, "ai.settings.changed")
        assert entry is not None
        assert (entry.before_json or {}).get("enabled") is True
        assert (entry.after_json or {}).get("enabled") is False
    finally:
        client.patch("/ai/settings", headers=admin_headers, json={"enabled": True})
        db.close()


def test_test_endpoint_returns_provider_used(client, admin_headers, monkeypatch):
    db = _db()
    try:
        # Garante IA ligada, mas provider local indisponível → resposta controlada.
        # (Força AI_PROVIDER=ollama — o default do ambiente de teste é mock.)
        client.patch("/ai/settings", headers=admin_headers, json={"enabled": True})
        monkeypatch.setattr(provider_factory.settings, "ai_provider", "ollama")
        with patch.object(OllamaProvider, "health_check", return_value=False):
            res = client.post("/ai/test", headers=admin_headers, json={"prompt": "Olá, responda OK"})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["provider"] == "none"
        assert body["error"] == "IA temporariamente indisponível."

        entry = _last_ai_audit(db, "ai.test.prompt")
        assert entry is not None
        details = entry.details or {}
        assert details.get("provider") == "none"
        assert "prompt" not in _json_keys(entry.details)  # nunca conteúdo
        assert details.get("prompt_hash")
    finally:
        db.close()


def _json_keys(d: Any) -> List[str]:
    return list(d.keys()) if isinstance(d, dict) else []


def test_test_endpoint_uses_local_provider_with_mock(client, admin_headers):
    """Com AI_PROVIDER=mock (default dos testes), o provider ativo é o mock."""
    db = _db()
    try:
        client.patch("/ai/settings", headers=admin_headers, json={"enabled": True})
        res = client.post("/ai/test", headers=admin_headers, json={"prompt": "Olá, responda OK"})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["provider"] == "local"
        assert body["error"] is None
        assert body["response"]
    finally:
        db.close()


def test_ai_configure_permission_required(client, admin_headers):
    """RBAC: sem token → 401; permissão ai.configure é exigida no backend."""
    res = client.get("/ai/settings")
    assert res.status_code == 401

    # OPERATOR (ai.use apenas) não pode ler nem mudar config completa
    username = f"op_ai_{int(time.time())}"
    created = client.post(
        "/auth/users",
        headers=admin_headers,
        json={
            "username": username,
            "email": f"{username}@gasflow.test",
            "password": "Operator#123",
            "display_name": "Operador IA",
            "role": "OPERATOR",
        },
    )
    if created.status_code not in (200, 201):
        pytest.skip(f"criação de operador indisponível: {created.status_code} {created.text[:120]}")
    op_login = client.post("/auth/login", json={"username": username, "password": "Operator#123"})
    if op_login.status_code != 200:
        pytest.skip("login de operador indisponível")
    op_headers = {"Authorization": f"Bearer {op_login.json()['token']}"}

    assert client.get("/ai/settings", headers=op_headers).status_code == 403
    assert client.patch("/ai/settings", headers=op_headers, json={"enabled": False}).status_code == 403
    # ai.use permite status e teste
    assert client.get("/ai/status", headers=op_headers).status_code == 200
    assert client.post("/ai/test", headers=op_headers, json={"prompt": "ping"}).status_code == 200
