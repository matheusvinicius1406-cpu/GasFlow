"""
WhatsApp Cloud API Webhook — FastAPI integration tests.

Cobre: handshake de verificação (hub.challenge), validação HMAC de assinatura,
fail-closed sem secret, corpo inválido, parsing end-to-end de statuses e
mensagens recebidas. Não faz chamadas reais à Meta.
"""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

APP_SECRET = "test-app-secret"
VERIFY_TOKEN = "test-verify-token"


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _status_payload() -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {
                                    "id": "wamid.STATUS1",
                                    "status": "delivered",
                                    "recipient_id": "5591999999999",
                                    "timestamp": "1700000000",
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def _message_payload() -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": "wamid.IN1",
                                    "from": "5591999999999",
                                    "type": "text",
                                    "text": {"body": "Pedido 42 chegou?"},
                                    "timestamp": "1700000000",
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("WHATSAPP_CLOUD_API_APP_SECRET", APP_SECRET)
    monkeypatch.setenv("WHATSAPP_CLOUD_API_VERIFY_TOKEN", VERIFY_TOKEN)
    # Reimporta o módulo para recapturar os env vars lidos no import.
    import importlib

    import app.presentation.api.whatsapp_cloud_webhook as webhook_module

    importlib.reload(webhook_module)
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(webhook_module.router)
    return TestClient(app)


@pytest.fixture
def client_unconfigured(monkeypatch) -> TestClient:
    monkeypatch.delenv("WHATSAPP_CLOUD_API_APP_SECRET", raising=False)
    monkeypatch.delenv("WHATSAPP_CLOUD_API_VERIFY_TOKEN", raising=False)
    import importlib

    import app.presentation.api.whatsapp_cloud_webhook as webhook_module

    importlib.reload(webhook_module)
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(webhook_module.router)
    return TestClient(app)


class TestVerifyHandshake:
    def test_valid_subscription_returns_challenge(self, client: TestClient):
        resp = client.get(
            "/whatsapp/cloud-api/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": "CHALLENGE_123",
            },
        )
        assert resp.status_code == 200
        assert resp.text == "CHALLENGE_123"

    def test_wrong_token_is_403(self, client: TestClient):
        resp = client.get(
            "/whatsapp/cloud-api/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong",
                "hub.challenge": "CHALLENGE_123",
            },
        )
        assert resp.status_code == 403

    def test_wrong_mode_is_403(self, client: TestClient):
        resp = client.get(
            "/whatsapp/cloud-api/webhook",
            params={
                "hub.mode": "denied",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": "C",
            },
        )
        assert resp.status_code == 403


class TestEventReception:
    def test_valid_signed_status_event(self, client: TestClient):
        body = json.dumps(_status_payload()).encode()
        resp = client.post(
            "/whatsapp/cloud-api/webhook",
            content=body,
            headers={"X-Hub-Signature-256": _sign(APP_SECRET, body), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["statuses"] == 1
        assert data["messages"] == 0

    def test_valid_signed_incoming_message(self, client: TestClient):
        body = json.dumps(_message_payload()).encode()
        resp = client.post(
            "/whatsapp/cloud-api/webhook",
            content=body,
            headers={"X-Hub-Signature-256": _sign(APP_SECRET, body), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["messages"] == 1

    def test_missing_signature_is_403(self, client: TestClient):
        resp = client.post(
            "/whatsapp/cloud-api/webhook",
            content=json.dumps(_status_payload()).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 403

    def test_tampered_payload_is_403(self, client: TestClient):
        body = json.dumps(_status_payload()).encode()
        bad_sig = _sign(APP_SECRET, b'{"entry": []}')  # assinatura de outro corpo
        resp = client.post(
            "/whatsapp/cloud-api/webhook",
            content=body,
            headers={"X-Hub-Signature-256": bad_sig},
        )
        assert resp.status_code == 403

    def test_invalid_json_with_valid_signature_is_400(self, client: TestClient):
        body = b"not-json"
        resp = client.post(
            "/whatsapp/cloud-api/webhook",
            content=body,
            headers={"X-Hub-Signature-256": _sign(APP_SECRET, body)},
        )
        assert resp.status_code == 400


class TestFailClosed:
    def test_post_without_secret_is_503(self, client_unconfigured: TestClient):
        resp = client_unconfigured.post(
            "/whatsapp/cloud-api/webhook",
            content=b"{}",
            headers={"X-Hub-Signature-256": "sha256=" + "0" * 64},
        )
        assert resp.status_code == 503
        assert resp.json()["error"] == "webhook_not_configured"

    def test_get_without_verify_token_is_403(self, client_unconfigured: TestClient):
        resp = client_unconfigured.get(
            "/whatsapp/cloud-api/webhook",
            params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "c"},
        )
        assert resp.status_code == 403
