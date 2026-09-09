"""
Leads API Tests — captura pública do site institucional.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200
    return res.json()["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestPublicLeads:
    def test_newsletter_ok(self, client):
        res = client.post(
            "/leads",
            json={"email": "lead1@example.com", "source": "site_institucional"},
        )
        assert res.status_code == 201
        assert res.json()["success"] is True

    def test_newsletter_invalid_email(self, client):
        res = client.post("/leads", json={"email": "sem-arroba"})
        assert res.status_code == 422

    def test_newsletter_honeypot_rejected(self, client):
        res = client.post(
            "/leads",
            json={"email": "bot@example.com", "website": "http://spam.example"},
        )
        assert res.status_code == 400

    def test_demo_request_ok(self, client):
        res = client.post(
            "/demo-request",
            json={
                "email": "demo@example.com",
                "name": "Fulano",
                "phone": "11988887777",
                "message": "Quero ver o sistema",
            },
        )
        assert res.status_code == 201
        assert res.json()["success"] is True

    def test_demo_request_honeypot_rejected(self, client):
        res = client.post(
            "/demo-request",
            json={"email": "bot2@example.com", "website": "x"},
        )
        assert res.status_code == 400

    def test_admin_list_leads(self, client, admin_token):
        res = client.get("/leads", headers=_auth(admin_token))
        assert res.status_code == 200
        emails = {item["email"] for item in res.json()["leads"]}
        assert "lead1@example.com" in emails

    def test_admin_list_requires_auth(self, client):
        assert client.get("/leads").status_code == 401
