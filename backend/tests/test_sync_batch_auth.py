"""
sync-batch Auth Matrix — endpoint de máquina-para-máquina.

POST /clients/contacts/sync-batch deve:
- aceitar SOMENTE a chave de serviço (X-GasFlow-Key igual a
  WHATSAPP_SERVICE_KEY/MARCOS_GAS_API_KEY do backend);
- rejeitar JWT válido de usuário (sem fallback Bearer) — um token vazado
  não pode sobrescrever o CRM em lote;
- rejeitar requisições anônimas;
- ficar indisponível (fail-closed) quando a chave não está configurada.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200
    return res.json()["token"]


def _post(client, headers):
    return client.post(
        "/clients/contacts/sync-batch",
        json={"contacts": [{"telefone": "11999999999", "nome": "Teste"}]},
        headers=headers,
    )


class TestSyncBatchAuthMatrix:
    def test_service_key_accepted(self, client, monkeypatch):
        monkeypatch.setattr(settings, "whatsapp_service_key", "secret-key-123")
        res = _post(client, {"X-GasFlow-Key": "secret-key-123"})
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["results"][0]["action"] in ("created", "updated", "unchanged")

    def test_wrong_key_rejected(self, client, monkeypatch):
        monkeypatch.setattr(settings, "whatsapp_service_key", "secret-key-123")
        res = _post(client, {"X-GasFlow-Key": "wrong-key"})
        assert res.status_code == 401

    def test_valid_jwt_rejected(self, client, admin_token):
        """JWT de usuário NÃO substitui a chave de serviço (sem fallback)."""
        res = _post(client, {"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 401

    def test_anonymous_rejected(self, client):
        res = _post(client, {})
        assert res.status_code == 401

    def test_unconfigured_key_fails_closed(self, client, monkeypatch):
        """Sem chave no backend, o endpoint fica indisponível — nunca aberto."""
        monkeypatch.setattr(settings, "whatsapp_service_key", "")
        res = _post(client, {"X-GasFlow-Key": "anything"})
        assert res.status_code == 401


class TestSyncBatchLastInteraction:
    """last_interaction_at deve virar datetime real (SQLite rejeita string ISO).

    Regressão: string ISO passava direto ao ORM e derrubava o INSERT com
    TypeError — o contato era descartado do lote em silêncio (errors:1).
    """

    def test_iso_timestamp_is_parsed_and_syncs(self, client, monkeypatch):
        monkeypatch.setattr(settings, "whatsapp_service_key", "secret-key-123")
        res = client.post(
            "/clients/contacts/sync-batch",
            json={
                "contacts": [
                    {
                        "telefone": "11990000001",
                        "nome": "Com Timestamp",
                        "last_interaction_at": "2026-09-05T10:00:00",
                    }
                ]
            },
            headers={"X-GasFlow-Key": "secret-key-123"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["errors"] == 0
        assert body["results"][0]["action"] in ("created", "updated", "unchanged")

    def test_tz_aware_timestamp_is_accepted(self, client, monkeypatch):
        monkeypatch.setattr(settings, "whatsapp_service_key", "secret-key-123")
        res = client.post(
            "/clients/contacts/sync-batch",
            json={
                "contacts": [
                    {
                        "telefone": "11990000002",
                        "nome": "Com TZ",
                        "last_interaction_at": "2026-09-05T10:00:00Z",
                    }
                ]
            },
            headers={"X-GasFlow-Key": "secret-key-123"},
        )
        assert res.status_code == 200
        assert res.json()["errors"] == 0

    def test_malformed_timestamp_dropped_but_contact_syncs(self, client, monkeypatch):
        """Valor inválido é descartado (sem 422, sem erro no item)."""
        monkeypatch.setattr(settings, "whatsapp_service_key", "secret-key-123")
        res = client.post(
            "/clients/contacts/sync-batch",
            json={
                "contacts": [
                    {
                        "telefone": "11990000003",
                        "nome": "Timestamp Ruim",
                        "last_interaction_at": "not-a-date",
                    }
                ]
            },
            headers={"X-GasFlow-Key": "secret-key-123"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["errors"] == 0
        assert body["results"][0]["action"] in ("created", "updated", "unchanged")
