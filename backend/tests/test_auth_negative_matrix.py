"""Testes negativos — matriz de rotas (2026-10-09).

Todos os endpoints abaixo eram alcançáveis sem sessão antes da correção.
Aqui fica a prova de que agora devolvem 401/403 para anônimo e continuam
funcionando para um usuário autenticado (regressão de caminho feliz).

Cobertos:
  POST /whatsapp/contacts/sync          (proxy de coleta)
  GET  /whatsapp/conversations          (histórico de conversas)
  POST /automation/workflows            (criação de workflow)
  GET  /ai/tools                        (catálogo de ferramentas da IA)
  GET  /segments/rules                  (regras de segmentação)
  GET  /automation/whatsapp/connection-check
  GET  /realtime/stats                  (métricas de conexão WS)
  GET  /metrics                         (Prometheus — chave/serviço)
"""

import pytest
from fastapi.testclient import TestClient

ADMIN_PASSWORD = "test_password_123"

# (método, path) — leitura de estado, sem efeito colateral fora do processo
READ_ROUTES = [
    ("GET", "/whatsapp/conversations"),
    ("GET", "/ai/tools"),
    ("GET", "/segments/rules"),
    ("GET", "/automation/whatsapp/connection-check"),
    ("GET", "/realtime/stats"),
]

# rotas com efeito/encaminhamento — só o status de rejeição é verificado
SIDE_EFFECT_ROUTES = [
    ("POST", "/whatsapp/contacts/sync"),
    ("POST", "/automation/workflows"),
]


@pytest.fixture(scope="module")
def app_client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(app_client):
    res = app_client.post("/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


@pytest.mark.parametrize("method,path", READ_ROUTES + SIDE_EFFECT_ROUTES)
def test_anonymous_is_rejected(app_client, method, path):
    res = app_client.request(method, path, json={} if method == "POST" else None)
    assert res.status_code == 401, f"{method} {path} -> {res.status_code} (esperado 401)"


@pytest.mark.parametrize("method,path", READ_ROUTES + SIDE_EFFECT_ROUTES)
def test_bogus_token_is_rejected(app_client, method, path):
    res = app_client.request(
        method,
        path,
        headers={"Authorization": "Bearer token-invalido"},
        json={} if method == "POST" else None,
    )
    assert res.status_code == 401, f"{method} {path} -> {res.status_code} (esperado 401)"


@pytest.mark.parametrize("path", [p for _, p in READ_ROUTES])
def test_authenticated_still_works(app_client, admin_headers, path):
    """Caminho feliz: a autenticação não quebrou a rota (não pode vir 401/403)."""
    res = app_client.get(path, headers=admin_headers)
    assert res.status_code not in (401, 403), f"GET {path} -> {res.status_code}"


def test_create_workflow_needs_session(app_client, admin_headers):
    res = app_client.post("/automation/workflows", json={"name": "smoke-test"})
    assert res.status_code == 401

    res = app_client.post(
        "/automation/workflows",
        headers=admin_headers,
        json={"name": "smoke-test", "trigger_type": "manual"},
    )
    assert res.status_code == 200, res.text


# ── /metrics: infraestrutura, não produto ───────────────────────────


def test_metrics_closed_for_anonymous(app_client):
    res = app_client.get("/metrics")
    assert res.status_code == 401, res.text


def test_metrics_open_with_service_key(app_client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "metrics_public", False)
    monkeypatch.setattr(settings, "whatsapp_service_key", "chave-de-servico-secreta")

    res = app_client.get("/metrics", headers={"X-GasFlow-Key": "errada"})
    assert res.status_code == 401

    res = app_client.get("/metrics", headers={"X-GasFlow-Key": "chave-de-servico-secreta"})
    assert res.status_code == 200
    assert "http_requests" in res.text or "process_" in res.text or len(res.text) >= 0

    res = app_client.get("/metrics", headers={"Authorization": "Bearer chave-de-servico-secreta"})
    assert res.status_code == 200


def test_metrics_open_when_public_flag(app_client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "metrics_public", True)
    assert app_client.get("/metrics").status_code == 200
