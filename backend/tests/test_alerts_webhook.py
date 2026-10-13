"""
Alerts Webhook (Alertmanager receiver) — unit tests.

Cobre: payload padrão do Alertmanager (firing/resolved), JSON inválido e
rota registrada no app principal.
"""

import pytest
from fastapi import FastAPI

from app.presentation.api.alerts_webhook import router
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _alertmanager_payload(status: str = "firing") -> dict:
    return {
        "version": "4",
        "groupKey": "gasflow_alerts:whatsapp",
        "status": status,
        "receiver": "gasflow-backend",
        "alerts": [
            {
                "status": status,
                "labels": {
                    "alertname": "WhatsappDisconnected",
                    "severity": "warning",
                    "account": "primary",
                },
                "annotations": {
                    "summary": "WhatsApp principal desconectado",
                    "description": "A conta primary está sem conexão há mais de 2 minutos.",
                },
            }
        ],
    }


class TestAlertsWebhook:
    def test_firing_alert_accepted(self, client: TestClient):
        resp = client.post("/webhooks/alerts", json=_alertmanager_payload("firing"))
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "received": 1}

    def test_resolved_alert_accepted(self, client: TestClient):
        resp = client.post("/webhooks/alerts", json=_alertmanager_payload("resolved"))
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_invalid_json_rejected(self, client: TestClient):
        resp = client.post(
            "/webhooks/alerts",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_json"

    def test_empty_alerts_list_ok(self, client: TestClient):
        resp = client.post("/webhooks/alerts", json={"alerts": []})
        assert resp.status_code == 200
        assert resp.json()["received"] == 0

    def test_route_mounted_in_main_app(self):
        """Integração: a rota responde no app principal (com prefixo /api/v1)."""
        from app.main import app

        client = TestClient(app)
        resp = client.post("/api/v1/webhooks/alerts", json={"alerts": []})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "received": 0}


class TestAlertsWebhookOriginGate:
    """Gate de origem (matriz de rotas 2026-10-09).

    Sem segredo: dev aceita; produção responde 503 (fail-closed).
    Com segredo: exige X-Alert-Secret ou Bearer; ausente/errado = 401.
    """

    def test_secret_configured_rejects_missing(self, client: TestClient, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "alerts_webhook_secret", "s3cr3t")
        resp = client.post("/webhooks/alerts", json={"alerts": []})
        assert resp.status_code == 401
        assert resp.json()["error"] == "unauthorized"

    def test_secret_configured_rejects_wrong(self, client: TestClient, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "alerts_webhook_secret", "s3cr3t")
        resp = client.post(
            "/webhooks/alerts",
            json={"alerts": []},
            headers={"X-Alert-Secret": "errado"},
        )
        assert resp.status_code == 401

    def test_secret_configured_accepts_dedicated_header(self, client: TestClient, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "alerts_webhook_secret", "s3cr3t")
        resp = client.post(
            "/webhooks/alerts",
            json={"alerts": []},
            headers={"X-Alert-Secret": "s3cr3t"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "received": 0}

    def test_secret_configured_accepts_bearer(self, client: TestClient, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "alerts_webhook_secret", "s3cr3t")
        resp = client.post(
            "/webhooks/alerts",
            json={"alerts": []},
            headers={"Authorization": "Bearer s3cr3t"},
        )
        assert resp.status_code == 200

    def test_production_without_secret_is_fail_closed(self, client: TestClient, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "alerts_webhook_secret", "")
        monkeypatch.setattr(settings, "environment", "production")
        resp = client.post("/webhooks/alerts", json={"alerts": []})
        assert resp.status_code == 503
        assert resp.json()["error"] == "webhook_not_configured"

    def test_development_without_secret_still_accepts(self, client: TestClient, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "alerts_webhook_secret", "")
        monkeypatch.setattr(settings, "environment", "development")
        resp = client.post("/webhooks/alerts", json={"alerts": []})
        assert resp.status_code == 200
