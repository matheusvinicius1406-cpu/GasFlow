"""
Settings API Tests — Quadro de Configurações + RBAC granular.
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


class TestSettingsAuth:
    def test_requires_auth(self, client):
        assert client.get("/settings").status_code == 401

    def test_v1_alias_requires_auth(self, client):
        assert client.get("/api/v1/settings").status_code == 401


class TestSettingsSeedAndRead:
    def test_seed_defaults_auto(self, client, admin_token):
        res = client.get("/settings", headers=_auth(admin_token))
        assert res.status_code == 200
        cats = res.json()["categories"]
        # Defaults do seed presente nas categorias esperadas
        assert "general" in cats
        keys = {s["key"] for rows in cats.values() for s in rows}
        assert {
            "site_name",
            "timezone",
            "currency",
            "whatsapp_auto_reply",
            "pix_enabled",
            "dark_mode",
            "brand_color",
            "delivery_estimation_mode",
        } <= keys

    def test_get_key(self, client, admin_token):
        res = client.get("/settings/key/site_name", headers=_auth(admin_token))
        assert res.status_code == 200
        body = res.json()
        assert body["key"] == "site_name"
        assert body["value"] == "GasFlow"
        assert body["category"] == "general"

    def test_get_key_404(self, client, admin_token):
        assert client.get("/settings/key/nao_existe", headers=_auth(admin_token)).status_code == 404

    def test_get_category(self, client, admin_token):
        res = client.get("/settings/category/appearance", headers=_auth(admin_token))
        assert res.status_code == 200
        keys = {s["key"] for s in res.json()["settings"]}
        assert {"dark_mode", "brand_color"} <= keys

    def test_get_unknown_category_404(self, client, admin_token):
        res = client.get("/settings/category/nao_existe", headers=_auth(admin_token))
        assert res.status_code == 404


class TestSettingsWrite:
    def test_put_and_read_roundtrip(self, client, admin_token):
        res = client.put("/settings/key/site_name", json={"value": "GasFlow LTDA"}, headers=_auth(admin_token))
        assert res.status_code == 200
        assert res.json()["value"] == "GasFlow LTDA"
        assert res.json()["updated_by"]  # preenchido com o user_id do admin

        res = client.get("/settings/key/site_name", headers=_auth(admin_token))
        assert res.json()["value"] == "GasFlow LTDA"

        # restaura
        client.put("/settings/key/site_name", json={"value": "GasFlow"}, headers=_auth(admin_token))

    def test_put_bool_and_list_types(self, client, admin_token):
        res = client.put("/settings/key/dark_mode", json={"value": True}, headers=_auth(admin_token))
        assert res.json()["value"] is True
        client.put("/settings/key/dark_mode", json={"value": False}, headers=_auth(admin_token))

        res = client.put(
            "/settings/key/payment_methods",
            json={"value": ["PIX", "DINHEIRO"]},
            headers=_auth(admin_token),
        )
        assert res.json()["value"] == ["PIX", "DINHEIRO"]
        client.put(
            "/settings/key/payment_methods",
            json={"value": ["PIX", "DINHEIRO", "CARTAO"]},
            headers=_auth(admin_token),
        )

    def test_put_unknown_key_404(self, client, admin_token):
        res = client.put("/settings/key/nao_existe", json={"value": 1}, headers=_auth(admin_token))
        assert res.status_code == 404

    def test_seed_endpoint_idempotent(self, client, admin_token):
        # Já semeado no startup — segunda passada não cria nada.
        res = client.post("/settings/seed", headers=_auth(admin_token))
        assert res.status_code == 200
        assert res.json()["created"] == 0


class TestPermissionsEndpoints:
    def test_matrix_admin(self, client, admin_token):
        res = client.get("/settings/permissions/matrix", headers=_auth(admin_token))
        assert res.status_code == 200
        body = res.json()
        assert "ADMIN" in body["roles"]
        assert "settings.read" in body["roles"]["MANAGER"]
        assert "coupon.*" in body["roles"]["MANAGER"]
        assert body["me"]["role"] == "ADMIN"

    def test_me(self, client, admin_token):
        res = client.get("/settings/permissions/me", headers=_auth(admin_token))
        assert res.status_code == 200
        body = res.json()
        assert body["role"] == "ADMIN"
        assert isinstance(body["permissions"], list)


class TestWildcardPermissionFix:
    def test_resource_wildcard_matches_action(self):
        from app.domain.security.models import TenantContext, SystemRole

        ctx = TenantContext(role=SystemRole.MANAGER, permissions={"order.*"})
        assert ctx.has_permission("order.read") is True
        assert ctx.has_permission("order.create") is True
        assert ctx.has_permission("product.read") is False

    def test_admin_wildcard_grants_everything(self):
        from app.domain.security.models import TenantContext, SystemRole

        ctx = TenantContext(role=SystemRole.ADMIN, permissions={"admin.*"})
        assert ctx.has_permission("settings.write") is True
        assert ctx.has_permission("coupon.read") is True
        # Require_permission também concede por role == ADMIN (defesa dupla)

    def test_exact_and_nested_prefix(self):
        from app.domain.security.models import TenantContext, SystemRole

        ctx = TenantContext(role=SystemRole.DRIVER, permissions={"delivery.read.assigned"})
        assert ctx.has_permission("delivery.read.assigned") is True
        ctx2 = TenantContext(role=SystemRole.MANAGER, permissions={"delivery.*"})
        assert ctx2.has_permission("delivery.read.assigned") is True
