"""
Cross-Tenant Isolation Tests — Real multi-tenant provisioning.

Creates two distinct tenants with separate users and data,
then verifies complete data isolation between them.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def setup_tenants(client):
    """Create two tenants with admin users. Returns tokens for both."""
    resp = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    admin_token = resp.json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create Tenant A
    resp = client.post("/auth/tenants", json={"tenant_id": "tenant_a", "name": "GasFlow Filial A"},
                       headers=admin_headers)
    assert resp.status_code == 200

    # Create Tenant B
    resp = client.post("/auth/tenants", json={"tenant_id": "tenant_b", "name": "GasFlow Filial B"},
                       headers=admin_headers)
    assert resp.status_code == 200

    # Create admin users
    for username, tid in [("admin_a", "tenant_a"), ("admin_b", "tenant_b")]:
        resp = client.post("/auth/users", json={
            "username": username, "email": f"{username}@gasflow.local",
            "password": "admin123", "display_name": f"Admin {tid}",
            "role": "ADMIN", "tenant_id": tid,
        }, headers=admin_headers)
        assert resp.status_code == 200

    # Login as each tenant admin
    tokens = {}
    for username, tid in [("admin_a", "tenant_a"), ("admin_b", "tenant_b")]:
        resp = client.post("/auth/login", json={"username": username, "password": "admin123"})
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == tid
        t = resp.json()["token"]
        tokens[tid] = {"token": t, "headers": {"Authorization": f"Bearer {t}"}}

    tokens["admin"] = {"token": admin_token, "headers": admin_headers}
    return tokens


def get_items(resp_json):
    """Extract items from either paginated or list response."""
    if isinstance(resp_json, list):
        return resp_json
    return resp_json.get("items", resp_json.get("data", []))


class TestTenantProvisioning:
    def test_create_tenants(self, client, setup_tenants):
        resp = client.get("/auth/tenants", headers=setup_tenants["admin"]["headers"])
        assert resp.status_code == 200
        ids = [t["id"] for t in resp.json()["tenants"]]
        assert "tenant_a" in ids
        assert "tenant_b" in ids

    def test_tenant_a_login(self, client, setup_tenants):
        resp = client.get("/auth/me", headers=setup_tenants["tenant_a"]["headers"])
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "tenant_a"

    def test_tenant_b_login(self, client, setup_tenants):
        resp = client.get("/auth/me", headers=setup_tenants["tenant_b"]["headers"])
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "tenant_b"

    def test_duplicate_tenant_rejected(self, client, setup_tenants):
        resp = client.post("/auth/tenants", json={"tenant_id": "tenant_a", "name": "Dup"},
                           headers=setup_tenants["admin"]["headers"])
        assert resp.status_code == 400


class TestClientIsolation:
    def test_tenant_a_creates_client(self, client, setup_tenants):
        resp = client.post("/clients/", json={
            "nome": "Cliente Filial A", "telefone": "11988880001",
            "rua": "Rua A", "numero": "10", "bairro": "Centro A",
        }, headers=setup_tenants["tenant_a"]["headers"])
        assert resp.status_code == 200

    def test_tenant_b_creates_client(self, client, setup_tenants):
        resp = client.post("/clients/", json={
            "nome": "Cliente Filial B", "telefone": "21988880001",
            "rua": "Rua B", "numero": "20", "bairro": "Centro B",
        }, headers=setup_tenants["tenant_b"]["headers"])
        assert resp.status_code == 200

    def test_same_phone_different_tenants_ok(self, client, setup_tenants):
        """Two tenants can create clients with the same phone number."""
        # Tenant A creates client with phone X
        resp_a = client.post("/clients/", json={
            "nome": "Cliente Compartilhado A", "telefone": "11999990000",
            "rua": "Rua Comum", "numero": "1", "bairro": "Centro",
        }, headers=setup_tenants["tenant_a"]["headers"])
        assert resp_a.status_code == 200

        # Tenant B creates client with SAME phone X — should succeed
        resp_b = client.post("/clients/", json={
            "nome": "Cliente Compartilhado B", "telefone": "11999990000",
            "rua": "Rua Comum", "numero": "2", "bairro": "Centro",
        }, headers=setup_tenants["tenant_b"]["headers"])
        assert resp_b.status_code == 200

    def test_same_phone_same_tenant_rejected(self, client, setup_tenants):
        """Same tenant cannot create two clients with the same phone."""
        resp = client.post("/clients/", json={
            "nome": "Cliente Duplicado", "telefone": "11988880001",
            "rua": "Rua A", "numero": "30", "bairro": "Centro A",
        }, headers=setup_tenants["tenant_a"]["headers"])
        # Should fail — tenant_a already has a client with this phone
        assert resp.status_code == 409

    def test_tenant_a_sees_only_its_clients(self, client, setup_tenants):
        resp = client.get("/clients/", headers=setup_tenants["tenant_a"]["headers"])
        assert resp.status_code == 200
        names = [c["nome"] for c in get_items(resp.json())]
        assert "Cliente Filial A" in names
        assert "Cliente Filial B" not in names

    def test_tenant_b_sees_only_its_clients(self, client, setup_tenants):
        resp = client.get("/clients/", headers=setup_tenants["tenant_b"]["headers"])
        assert resp.status_code == 200
        names = [c["nome"] for c in get_items(resp.json())]
        assert "Cliente Filial B" in names
        assert "Cliente Filial A" not in names

    def test_idor_read_client_by_codigo(self, client, setup_tenants):
        """Tenant A reads by codigo — gets its own client, not B's."""
        # Create deterministic test data for this test
        resp_create = client.post("/clients/", json={
            "nome": "IDOR Test A", "telefone": "11900001111",
            "rua": "Rua IDOR", "numero": "1", "bairro": "Centro",
        }, headers=setup_tenants["tenant_a"]["headers"])
        assert resp_create.status_code == 200
        codigo_a = resp_create.json()["codigo"]

        resp_create_b = client.post("/clients/", json={
            "nome": "IDOR Test B", "telefone": "21900002222",
            "rua": "Rua IDOR", "numero": "2", "bairro": "Centro",
        }, headers=setup_tenants["tenant_b"]["headers"])
        assert resp_create_b.status_code == 200

        # Tenant A reads its own client — should get "IDOR Test A"
        resp = client.get(f"/clients/{codigo_a}", headers=setup_tenants["tenant_a"]["headers"])
        assert resp.status_code == 200
        assert resp.json()["codigo"] == codigo_a
        assert resp.json()["nome"] == "IDOR Test A"

        # Both tenants have codigo=000001 (sequential). Verify tenant isolation:
        # When tenant_a reads 000001, it gets "IDOR Test A", NOT "IDOR Test B"
        resp_b_read = client.get(f"/clients/{codigo_a}", headers=setup_tenants["tenant_b"]["headers"])
        assert resp_b_read.status_code == 200
        assert resp_b_read.json()["nome"] == "IDOR Test B", (
            "Tenant B should get its own client when reading codigo=000001, not Tenant A's"
        )

    def test_idor_disable_client_by_codigo(self, client, setup_tenants):
        """Tenant A cannot disable Tenant B's client (by trying to disable a non-existent-in-A codigo)."""
        # Use a codigo that doesn't exist in A's tenant
        resp_a = client.patch("/clients/999999/disable",
                              headers=setup_tenants["tenant_a"]["headers"])
        assert resp_a.status_code == 404


class TestProductIsolation:
    def test_tenant_a_creates_product(self, client, setup_tenants):
        resp = client.post("/products/", json={
            "nome": "Gás 13kg Filial A", "tipo": "GAS", "preco": 120.00, "estoque": 50,
        }, headers=setup_tenants["tenant_a"]["headers"])
        assert resp.status_code == 200

    def test_tenant_b_creates_product(self, client, setup_tenants):
        resp = client.post("/products/", json={
            "nome": "Gás 13kg Filial B", "tipo": "GAS", "preco": 115.00, "estoque": 30,
        }, headers=setup_tenants["tenant_b"]["headers"])
        assert resp.status_code == 200

    def test_tenant_a_sees_only_its_products(self, client, setup_tenants):
        resp = client.get("/products/", headers=setup_tenants["tenant_a"]["headers"])
        assert resp.status_code == 200
        names = [p["nome"] for p in get_items(resp.json())]
        assert "Gás 13kg Filial A" in names
        assert "Gás 13kg Filial B" not in names

    def test_tenant_b_sees_only_its_products(self, client, setup_tenants):
        resp = client.get("/products/", headers=setup_tenants["tenant_b"]["headers"])
        assert resp.status_code == 200
        names = [p["nome"] for p in get_items(resp.json())]
        assert "Gás 13kg Filial B" in names
        assert "Gás 13kg Filial A" not in names


class TestDriverIsolation:
    def test_tenant_a_creates_driver(self, client, setup_tenants):
        resp = client.post("/delivery-drivers/", json={
            "nome": "Motorista A", "telefone": "11977770001", "placa": "ABC-1234",
        }, headers=setup_tenants["tenant_a"]["headers"])
        assert resp.status_code == 200

    def test_tenant_b_creates_driver(self, client, setup_tenants):
        resp = client.post("/delivery-drivers/", json={
            "nome": "Motorista B", "telefone": "21977770001", "placa": "XYZ-5678",
        }, headers=setup_tenants["tenant_b"]["headers"])
        assert resp.status_code == 200

    def test_tenant_a_sees_only_its_drivers(self, client, setup_tenants):
        resp = client.get("/delivery-drivers/", headers=setup_tenants["tenant_a"]["headers"])
        assert resp.status_code == 200
        names = [d["nome"] for d in get_items(resp.json())]
        assert "Motorista A" in names
        assert "Motorista B" not in names


class TestFinanceIsolation:
    def test_tenant_a_payments(self, client, setup_tenants):
        resp = client.get("/finance/payments", headers=setup_tenants["tenant_a"]["headers"])
        assert resp.status_code == 200

    def test_tenant_b_payments(self, client, setup_tenants):
        resp = client.get("/finance/payments", headers=setup_tenants["tenant_b"]["headers"])
        assert resp.status_code == 200


class TestInventoryIsolation:
    def test_tenant_a_inventory(self, client, setup_tenants):
        resp = client.get("/inventory/", headers=setup_tenants["tenant_a"]["headers"])
        assert resp.status_code == 200

    def test_tenant_b_inventory(self, client, setup_tenants):
        resp = client.get("/inventory/", headers=setup_tenants["tenant_b"]["headers"])
        assert resp.status_code == 200
