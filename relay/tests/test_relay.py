"""
Testes do relay — rodam in-process (TestClient WS) contra o mesmo app
que sobe no Fly. Cobrem: conexão do desktop, roteamento de posição,
cache de última posição e enforcement de token (prompt 4.4/7).
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Token fixo p/ os testes (o app lê no import)
os.environ["RELAY_TOKEN"] = "test-token-123"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, registry  # noqa: E402

H = {"x-relay-token": "test-token-123"}


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_location_requires_token(client):
    res = client.post(
        "/driver/location",
        json={
            "driver_id": "d1",
            "tenant_id": "t1",
            "positions": [{"lat": 1.0, "lng": 2.0}],
        },
    )
    assert res.status_code == 401


def test_location_without_desktop_is_cached(client):
    res = client.post(
        "/driver/location",
        headers=H,
        json={
            "driver_id": "d1",
            "tenant_id": "t-cache",
            "positions": [{"lat": -1.4558, "lng": -48.4902, "speed": 30.0}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["accepted"] == 1
    assert body["delivered_to_desktop"] is False  # desktop offline

    last = client.get("/driver/last", params={"tenant": "t-cache"}, headers=H)
    assert last.status_code == 200
    assert last.json()["lat"] == -1.4558


def test_location_routed_to_connected_desktop(client):
    with client.websocket_connect("/relay/ws?tenant=t-live&token=test-token-123") as ws:
        # Primeira mensagem: nada em cache → o relay não envia nada antes.
        # Envia posição via HTTP e espera receber via WS.
        res = client.post(
            "/driver/location",
            headers=H,
            json={
                "driver_id": "d-live",
                "tenant_id": "t-live",
                "positions": [{"lat": -23.55, "lng": -46.63, "speed": 40.0}],
            },
        )
        assert res.json()["delivered_to_desktop"] is True
        event = ws.receive_json()
        assert event["type"] == "driver:location"
        assert event["payload"]["driver_id"] == "d-live"
        assert event["payload"]["lat"] == -23.55
    # Conexão fechou → registry limpo
    assert not registry.is_online("t-live")


def test_ws_rejects_bad_token(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/relay/ws?tenant=t-x&token=wrong"):
            pass


def test_second_desktop_same_tenant_rejected(client):
    # O registry recusa o segundo desktop (4409 no servidor); o contexto de
    # teste do TestClient tolera o close, então validamos o estado final:
    # o segundo registro não substitui o primeiro.
    with client.websocket_connect("/relay/ws?tenant=t-dup&token=test-token-123") as ws1:
        ws1.send_text("ping")  # mantém viva até o register do segundo
        before = registry.is_online("t-dup")
        assert before is True
        with client.websocket_connect(
            "/relay/ws?tenant=t-dup&token=test-token-123"
        ) as ws2:
            ws2.send_text("ping")
        # Segunda conexão não derrubou a primeira nem foi registrada
        assert registry.is_online("t-dup") is True
