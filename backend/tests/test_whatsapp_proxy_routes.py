"""Contract tests — rotas proxy do WhatsApp.

O backend expõe /whatsapp/* como proxy para o serviço WhatsApp externo.
Estes testes garantem que as rotas existem e encaminham o path correto
(evita 404 do frontend quando o proxy fica sem uma rota que o FE consome,
ex.: detalhe de campanha, destinatários e detalhe de lista).

Segurança (matriz de rotas 2026-10-09): o router inteiro exige sessão
(`whatsapp.read`) e o envio exige `whatsapp.send`. Aqui fica a prova:
401 sem token, 403 sem permissão, 200 com credencial.
"""

import pytest
from fastapi.testclient import TestClient

ADMIN_PASSWORD = "test_password_123"


@pytest.fixture()
def client(monkeypatch):
    """TestClient com o _proxy_get stubbed para ecoar o path encaminhado."""
    import app.presentation.api.whatsapp.accounts as whatsapp_module

    captured = {}

    async def fake_proxy_get(path: str) -> dict:
        captured["path"] = path
        return {"echo": path}

    monkeypatch.setattr(whatsapp_module, "_proxy_get", fake_proxy_get)
    from app.main import app

    return TestClient(app), captured


def _token(test_client: TestClient) -> str:
    res = test_client.post("/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert res.status_code == 200, res.text
    return res.json()["token"]


@pytest.fixture()
def auth_headers(client):
    test_client, _ = client
    return {"Authorization": f"Bearer {_token(test_client)}"}


def test_campaign_detail_route_exists(client, auth_headers):
    test_client, captured = client
    response = test_client.get("/whatsapp/campaigns/42", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"echo": "/campaigns/42"}
    assert captured["path"] == "/campaigns/42"


def test_campaign_recipients_route_exists(client, auth_headers):
    test_client, captured = client
    response = test_client.get("/whatsapp/campaigns/42/recipients", headers=auth_headers)
    assert response.status_code == 200
    assert captured["path"] == "/campaigns/42/recipients"


def test_campaign_results_route_exists(client, auth_headers):
    test_client, captured = client
    response = test_client.get("/whatsapp/campaigns/42/results", headers=auth_headers)
    assert response.status_code == 200
    assert captured["path"] == "/campaigns/42/results"


def test_list_detail_route_exists(client, auth_headers):
    test_client, captured = client
    response = test_client.get("/whatsapp/lists/7", headers=auth_headers)
    assert response.status_code == 200
    assert captured["path"] == "/lists/7"


def test_list_campaigns_still_lists(client, auth_headers):
    test_client, captured = client
    response = test_client.get("/whatsapp/campaigns", headers=auth_headers)
    assert response.status_code == 200
    assert captured["path"] == "/campaigns"


# ── Negativos: o proxy era anônimo antes da matriz de rotas ──────────


def test_proxy_rejects_anonymous(client):
    test_client, captured = client
    response = test_client.get("/whatsapp/campaigns")
    assert response.status_code == 401
    assert "path" not in captured


def test_proxy_rejects_bogus_token(client):
    test_client, captured = client
    response = test_client.get("/whatsapp/campaigns", headers={"Authorization": "Bearer nao-e-token"})
    assert response.status_code == 401
    assert "path" not in captured


def test_proxy_rejects_role_without_permission(client, auth_headers):
    """DRIVER não tem whatsapp.read → 403 (não 200, não 404)."""
    test_client, captured = client
    import uuid

    username = f"drv_{uuid.uuid4().hex[:8]}"
    res = test_client.post(
        "/admin/users",
        headers=auth_headers,
        json={
            "username": username,
            "email": f"{username}@x.local",
            "password": "StrongPass1!",
            "role": "DRIVER",
        },
    )
    assert res.status_code in (200, 201), res.text

    res = test_client.post("/auth/login", json={"username": username, "password": "StrongPass1!"})
    assert res.status_code == 200, res.text
    headers = {"Authorization": f"Bearer {res.json()['token']}"}

    response = test_client.get("/whatsapp/campaigns", headers=headers)
    assert response.status_code == 403, response.text
    assert "path" not in captured
