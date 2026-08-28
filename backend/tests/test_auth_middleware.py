"""
Auth Middleware Tests — Regression coverage for authentication and authorization.
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
    """Login once and reuse token across all tests in this module."""
    res = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200
    return res.json()["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


# ── Public Endpoints ────────────────────────────────

class TestPublicEndpoints:
    def test_health(self, client):
        assert client.get("/health").json()["status"] == "healthy"

    def test_root(self, client):
        assert client.get("/").json()["status"] == "online"

    def test_login(self, client):
        res = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
        assert res.status_code == 200
        assert res.json()["success"] is True


# ── Unauthenticated → 401 ──────────────────────────

class TestUnauthenticated:
    def test_clients(self, client):
        assert client.get("/clients/").status_code == 401

    def test_orders(self, client):
        assert client.get("/orders/").status_code == 401

    def test_products(self, client):
        assert client.get("/products/").status_code == 401

    def test_inventory(self, client):
        assert client.get("/inventory/").status_code == 401

    def test_finance(self, client):
        assert client.get("/finance/payments").status_code == 401

    def test_delivery_drivers(self, client):
        assert client.get("/delivery-drivers/").status_code == 401

    def test_automation(self, client):
        assert client.get("/automation/workflows").status_code == 401

    def test_ai_chat(self, client):
        assert client.post("/ai/chat", json={"message": "test"}).status_code == 401


# ── Invalid Token → 401 ─────────────────────────────

class TestInvalidToken:
    def test_invalid_token(self, client):
        assert client.get("/clients/", headers=_auth("invalid")).status_code == 401

    def test_empty_bearer(self, client):
        assert client.get("/clients/", headers={"Authorization": "Bearer "}).status_code == 401


# ── Valid Token → 200 ───────────────────────────────

class TestValidToken:
    def test_clients(self, client, admin_token):
        res = client.get("/clients/", headers=_auth(admin_token))
        assert res.status_code == 200
        assert "items" in res.json()

    def test_orders(self, client, admin_token):
        assert client.get("/orders/", headers=_auth(admin_token)).status_code == 200

    def test_products(self, client, admin_token):
        assert client.get("/products/", headers=_auth(admin_token)).status_code == 200

    def test_inventory(self, client, admin_token):
        assert client.get("/inventory/", headers=_auth(admin_token)).status_code == 200

    def test_finance(self, client, admin_token):
        assert client.get("/finance/payments", headers=_auth(admin_token)).status_code == 200

    def test_auth_me(self, client, admin_token):
        res = client.get("/auth/me", headers=_auth(admin_token))
        assert res.status_code == 200
        assert res.json()["username"] == "admin"


# ── Authorization / RBAC ────────────────────────────

class TestRBAC:
    def test_admin_accesses_users(self, client, admin_token):
        res = client.get("/auth/users", headers=_auth(admin_token))
        assert res.status_code == 200
        assert "users" in res.json()

    def test_admin_accesses_audit(self, client, admin_token):
        res = client.get("/auth/audit", headers=_auth(admin_token))
        assert res.status_code == 200
        assert "records" in res.json()

    def test_admin_accesses_roles(self, client, admin_token):
        res = client.get("/auth/roles", headers=_auth(admin_token))
        assert res.status_code == 200
        assert "roles" in res.json()
