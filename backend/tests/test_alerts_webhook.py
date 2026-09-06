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
