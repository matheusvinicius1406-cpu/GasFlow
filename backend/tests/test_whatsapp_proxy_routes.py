"""Contract tests — rotas proxy do WhatsApp.

O backend expõe /whatsapp/* como proxy para o serviço WhatsApp externo.
Estes testes garantem que as rotas existem e encaminham o path correto
(evita 404 do frontend quando o proxy fica sem uma rota que o FE consome,
ex.: detalhe de campanha, destinatários e detalhe de lista).
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    """TestClient com o _proxy_get stubbed para ecoar o path encaminhado."""
    import app.presentation.api.whatsapp as whatsapp_module

    captured = {}

    async def fake_proxy_get(path: str) -> dict:
        captured["path"] = path
        return {"echo": path}

    monkeypatch.setattr(whatsapp_module, "_proxy_get", fake_proxy_get)
    from app.main import app

    return TestClient(app), captured


def test_campaign_detail_route_exists(client):
    test_client, captured = client
    response = test_client.get("/whatsapp/campaigns/42")
    assert response.status_code == 200
    assert response.json() == {"echo": "/campaigns/42"}
    assert captured["path"] == "/campaigns/42"


def test_campaign_recipients_route_exists(client):
    test_client, captured = client
    response = test_client.get("/whatsapp/campaigns/42/recipients")
    assert response.status_code == 200
    assert captured["path"] == "/campaigns/42/recipients"


def test_campaign_results_route_exists(client):
    test_client, captured = client
    response = test_client.get("/whatsapp/campaigns/42/results")
    assert response.status_code == 200
    assert captured["path"] == "/campaigns/42/results"


def test_list_detail_route_exists(client):
    test_client, captured = client
    response = test_client.get("/whatsapp/lists/7")
    assert response.status_code == 200
    assert captured["path"] == "/lists/7"


def test_list_campaigns_still_lists(client):
    test_client, captured = client
    response = test_client.get("/whatsapp/campaigns")
    assert response.status_code == 200
    assert captured["path"] == "/campaigns"
