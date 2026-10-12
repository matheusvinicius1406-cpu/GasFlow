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
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def setup_tenants(client):
    """Create two tenants with admin users. Returns tokens for both."""
    # Ensure rate limiter is clear before any logins in this module
    try:
        import app.presentation.dependencies as deps

        if deps._auth_service is not None:
            deps._auth_service._rate_limiter._buckets.clear()
    except Exception:
        pass
    resp = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert resp.status_code == 200
    admin_token = resp.json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create Tenant A (idempotent: 200 = created, 400 = already exists)
    resp = client.post(
        "/auth/tenants", json={"tenant_id": "tenant_a", "name": "GasFlow Filial A"}, headers=admin_headers
    )
    assert resp.status_code in (200, 400)

    # Create Tenant B
    resp = client.post(
        "/auth/tenants", json={"tenant_id": "tenant_b", "name": "GasFlow Filial B"}, headers=admin_headers
    )
    assert resp.status_code in (200, 400)

    # Create admin users (idempotent)
    for username, tid in [("admin_a", "tenant_a"), ("admin_b", "tenant_b")]:
        resp = client.post(
            "/auth/users",
            json={
                "username": username,
                "email": f"{username}@gasflow.local",
                "password": "test_password_123",
                "display_name": f"Admin {tid}",
                "role": "ADMIN",
                "tenant_id": tid,
            },
            headers=admin_headers,
        )
        assert resp.status_code in (200, 400)

    # Reset rate limiter before tenant admin logins
    try:
        import app.presentation.dependencies as deps

        if deps._auth_service is not None:
            deps._auth_service._rate_limiter._buckets.clear()
    except Exception:
        pass

    # Login as each tenant admin
    tokens = {}
    for username, tid in [("admin_a", "tenant_a"), ("admin_b", "tenant_b")]:
        resp = client.post("/auth/login", json={"username": username, "password": "test_password_123"})
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
        resp = client.post(
            "/auth/tenants", json={"tenant_id": "tenant_a", "name": "Dup"}, headers=setup_tenants["admin"]["headers"]
        )
        assert resp.status_code == 400


class TestClientIsolation:
    def test_tenant_a_creates_client(self, client, setup_tenants):
        resp = client.post(
            "/clients/",
            json={
                "nome": "Cliente Filial A",
                "telefone": "11988880001",
                "rua": "Rua A",
                "numero": "10",
                "bairro": "Centro A",
            },
            headers=setup_tenants["tenant_a"]["headers"],
        )
        assert resp.status_code == 200

    def test_tenant_b_creates_client(self, client, setup_tenants):
        resp = client.post(
            "/clients/",
            json={
                "nome": "Cliente Filial B",
                "telefone": "21988880001",
                "rua": "Rua B",
                "numero": "20",
                "bairro": "Centro B",
            },
            headers=setup_tenants["tenant_b"]["headers"],
        )
        assert resp.status_code == 200

    def test_same_phone_different_tenants_ok(self, client, setup_tenants):
        """Two tenants can create clients with the same phone number."""
        # Tenant A creates client with phone X
        resp_a = client.post(
            "/clients/",
            json={
                "nome": "Cliente Compartilhado A",
                "telefone": "11999990000",
                "rua": "Rua Comum",
                "numero": "1",
                "bairro": "Centro",
            },
            headers=setup_tenants["tenant_a"]["headers"],
        )
        assert resp_a.status_code == 200

        # Tenant B creates client with SAME phone X — should succeed
        resp_b = client.post(
            "/clients/",
            json={
                "nome": "Cliente Compartilhado B",
                "telefone": "11999990000",
                "rua": "Rua Comum",
                "numero": "2",
                "bairro": "Centro",
            },
            headers=setup_tenants["tenant_b"]["headers"],
        )
        assert resp_b.status_code == 200

    def test_same_phone_same_tenant_rejected(self, client, setup_tenants):
        """Same tenant cannot create two clients with the same phone."""
        resp = client.post(
            "/clients/",
            json={
                "nome": "Cliente Duplicado",
                "telefone": "11988880001",
                "rua": "Rua A",
                "numero": "30",
                "bairro": "Centro A",
            },
            headers=setup_tenants["tenant_a"]["headers"],
        )
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
        resp_create = client.post(
            "/clients/",
            json={
                "nome": "IDOR Test A",
                "telefone": "11900001111",
                "rua": "Rua IDOR",
                "numero": "1",
                "bairro": "Centro",
            },
            headers=setup_tenants["tenant_a"]["headers"],
        )
        assert resp_create.status_code == 200
        codigo_a = resp_create.json()["codigo"]

        resp_create_b = client.post(
            "/clients/",
            json={
                "nome": "IDOR Test B",
                "telefone": "21900002222",
                "rua": "Rua IDOR",
                "numero": "2",
                "bairro": "Centro",
            },
            headers=setup_tenants["tenant_b"]["headers"],
        )
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
        resp_a = client.patch("/clients/999999/disable", headers=setup_tenants["tenant_a"]["headers"])
        assert resp_a.status_code == 404


class TestProductIsolation:
    def test_tenant_a_creates_product(self, client, setup_tenants):
        resp = client.post(
            "/products/",
            json={
                "nome": "Gás 13kg Filial A",
                "tipo": "GAS",
                "preco": 120.00,
                "estoque": 50,
            },
            headers=setup_tenants["tenant_a"]["headers"],
        )
        assert resp.status_code == 200

    def test_tenant_b_creates_product(self, client, setup_tenants):
        resp = client.post(
            "/products/",
            json={
                "nome": "Gás 13kg Filial B",
                "tipo": "GAS",
                "preco": 115.00,
                "estoque": 30,
            },
            headers=setup_tenants["tenant_b"]["headers"],
        )
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
        resp = client.post(
            "/delivery-drivers/",
            json={
                "nome": "Motorista A",
                "telefone": "11977770001",
                "placa": "ABC-1234",
            },
            headers=setup_tenants["tenant_a"]["headers"],
        )
        assert resp.status_code == 200

    def test_tenant_b_creates_driver(self, client, setup_tenants):
        resp = client.post(
            "/delivery-drivers/",
            json={
                "nome": "Motorista B",
                "telefone": "21977770001",
                "placa": "XYZ-5678",
            },
            headers=setup_tenants["tenant_b"]["headers"],
        )
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


# ═══════════════════════════════════════════════════════════
# P0 multiempresa (2026-10-10): WhatsApp + Automation
# ═══════════════════════════════════════════════════════════


class TestWhatsAppConversationIsolation:
    """Conversas WhatsApp são únicas e visíveis por (tenant, account, phone)."""

    def _create_conversation(self, tenant_id: str, phone: str):
        from app.domain.whatsapp.conversation import Conversation, ConversationState
        from app.infrastructure.database.connection import SessionLocal
        from app.infrastructure.whatsapp.repositories import SQLAlchemyConversationRepository

        db = SessionLocal()
        try:
            repo = SQLAlchemyConversationRepository(db, tenant_id)
            conv = repo.create(
                Conversation(
                    tenant_id=tenant_id,
                    account_id="primary",
                    customer_phone=phone,
                    state=ConversationState.IDLE,
                )
            )
            if not hasattr(self, "_created_ids"):
                self._created_ids = []
            self._created_ids.append(conv.id)
            return conv
        finally:
            db.close()

    def _repo(self, tenant_id: str):
        from app.infrastructure.database.connection import SessionLocal
        from app.infrastructure.whatsapp.repositories import SQLAlchemyConversationRepository

        db = SessionLocal()
        self._dbs = getattr(self, "_dbs", [])
        self._dbs.append(db)
        return SQLAlchemyConversationRepository(db, tenant_id)

    def teardown_method(self):
        for db in getattr(self, "_dbs", []):
            db.close()
        self._dbs = []
        ids = getattr(self, "_created_ids", [])
        if ids:
            from app.infrastructure.database.connection import SessionLocal
            from app.infrastructure.repositories.whatsapp_model import WhatsAppConversationModel

            db = SessionLocal()
            try:
                db.query(WhatsAppConversationModel).filter(WhatsAppConversationModel.id.in_(ids)).delete(
                    synchronize_session=False
                )
                db.commit()
            finally:
                db.close()

    def test_same_phone_allowed_across_tenants(self):
        """Unicidade é por tenant: mesmo telefone em tenants diferentes é OK."""
        conv_a = self._create_conversation("tenant_a", "11912340001")
        conv_b = self._create_conversation("tenant_b", "11912340001")
        assert conv_a.tenant_id == "tenant_a"
        assert conv_b.tenant_id == "tenant_b"
        assert conv_a.id != conv_b.id

    def test_duplicate_phone_same_tenant_rejected(self):
        """Mesmo tenant não pode ter duas conversas abertas com o mesmo telefone."""
        import pytest
        from sqlalchemy.exc import IntegrityError

        self._create_conversation("tenant_a", "11912340002")
        with pytest.raises(IntegrityError):
            self._create_conversation("tenant_a", "11912340002")

    def test_find_by_phone_scoped(self):
        """find_by_phone_and_account só enxerga conversas do próprio tenant."""
        self._create_conversation("tenant_a", "11912340003")
        assert self._repo("tenant_a").find_by_phone_and_account("11912340003", "primary") is not None
        assert self._repo("tenant_b").find_by_phone_and_account("11912340003", "primary") is None

    def test_find_by_id_scoped(self):
        """find_by_id de outro tenant retorna None (sem vazar existência)."""
        conv = self._create_conversation("tenant_a", "11912340004")
        assert self._repo("tenant_a").find_by_id(conv.id) is not None
        assert self._repo("tenant_b").find_by_id(conv.id) is None

    def test_list_and_count_scoped(self):
        """Listagem e contagem de conversas ativas são por tenant."""
        conv_a = self._create_conversation("tenant_a", "11912340005")
        conversations_b, _total_b = self._repo("tenant_b").list_active()
        assert all(c.id != conv_a.id for c in conversations_b)
        assert conv_a.customer_phone not in [c.customer_phone for c in conversations_b]
        assert self._repo("tenant_b").count_active() == len(conversations_b)
        conversations_a, total_a = self._repo("tenant_a").list_active()
        assert any(c.id == conv_a.id for c in conversations_a)
        assert total_a >= 1

    def test_api_list_scoped(self, client, setup_tenants):
        """GET /whatsapp/conversations devolve só conversas do tenant do token."""
        conv = self._create_conversation("tenant_a", "11912340006")
        try:
            resp = client.get("/whatsapp/conversations", headers=setup_tenants["tenant_a"]["headers"])
            assert resp.status_code == 200
            phones_a = [c.get("customer_phone") or c.get("phone") for c in resp.json().get("conversations", [])]
            assert "11912340006" in phones_a

            resp = client.get("/whatsapp/conversations", headers=setup_tenants["tenant_b"]["headers"])
            assert resp.status_code == 200
            phones_b = [c.get("customer_phone") or c.get("phone") for c in resp.json().get("conversations", [])]
            assert "11912340006" not in phones_b
        finally:
            from app.infrastructure.database.connection import SessionLocal
            from app.infrastructure.repositories.whatsapp_model import WhatsAppConversationModel

            db = SessionLocal()
            try:
                db.query(WhatsAppConversationModel).filter(WhatsAppConversationModel.id == conv.id).delete()
                db.commit()
            finally:
                db.close()

    def test_api_detail_404_other_tenant(self, client, setup_tenants):
        """GET /whatsapp/conversations/{id} de outro tenant responde 404."""
        conv = self._create_conversation("tenant_a", "11912340007")
        try:
            resp = client.get(f"/whatsapp/conversations/{conv.id}", headers=setup_tenants["tenant_b"]["headers"])
            assert resp.status_code == 404

            resp = client.get(f"/whatsapp/conversations/{conv.id}", headers=setup_tenants["tenant_a"]["headers"])
            assert resp.status_code == 200
        finally:
            from app.infrastructure.database.connection import SessionLocal
            from app.infrastructure.repositories.whatsapp_model import WhatsAppConversationModel

            db = SessionLocal()
            try:
                db.query(WhatsAppConversationModel).filter(WhatsAppConversationModel.id == conv.id).delete()
                db.commit()
            finally:
                db.close()


class TestAutomationIsolation:
    """Workflows, kill switch, aprovações e runs de automação por tenant."""

    def test_workflows_scoped_per_tenant(self, client, setup_tenants):
        """Tenant B não enxerga workflow criado pelo tenant A; execute → 404."""
        resp = client.post(
            "/automation/workflows",
            json={"name": "WF Exclusivo A"},
            headers=setup_tenants["tenant_a"]["headers"],
        )
        assert resp.status_code == 200
        wf_id = resp.json()["id"]

        resp = client.get("/automation/workflows", headers=setup_tenants["tenant_b"]["headers"])
        assert resp.status_code == 200
        ids_b = [w["id"] for w in resp.json()["workflows"]]
        assert wf_id not in ids_b

        resp = client.post(
            f"/automation/workflows/{wf_id}/execute",
            json={},
            headers=setup_tenants["tenant_b"]["headers"],
        )
        assert resp.status_code == 404

        resp = client.post(
            f"/automation/workflows/{wf_id}/execute",
            json={},
            headers=setup_tenants["tenant_a"]["headers"],
        )
        assert resp.status_code == 200

    def test_kill_switch_per_tenant(self, client, setup_tenants):
        """Kill switch do tenant A não afeta (nem aparece para) o tenant B."""
        try:
            resp = client.post(
                "/automation/kill-switch",
                json={"active": True},
                headers=setup_tenants["tenant_a"]["headers"],
            )
            assert resp.status_code == 200
            assert resp.json()["active"] is True

            resp = client.get("/automation/kill-switch", headers=setup_tenants["tenant_b"]["headers"])
            assert resp.status_code == 200
            assert resp.json()["active"] is False

            resp = client.get("/automation/kill-switch", headers=setup_tenants["tenant_a"]["headers"])
            assert resp.status_code == 200
            assert resp.json()["active"] is True
        finally:
            client.post(
                "/automation/kill-switch",
                json={"active": False},
                headers=setup_tenants["tenant_a"]["headers"],
            )

        resp = client.get("/automation/kill-switch", headers=setup_tenants["tenant_a"]["headers"])
        assert resp.json()["active"] is False

    def test_metrics_per_tenant(self, client, setup_tenants):
        """Métricas e kill_switch do payload são os do tenant autenticado."""
        resp = client.get("/automation/metrics", headers=setup_tenants["tenant_a"]["headers"])
        assert resp.status_code == 200
        body_a = resp.json()
        resp = client.get("/automation/metrics", headers=setup_tenants["tenant_b"]["headers"])
        assert resp.status_code == 200
        body_b = resp.json()
        assert body_a["kill_switch"] is False
        assert body_b["kill_switch"] is False
        assert "workflow" in body_a and "agent" in body_a
        assert body_a["pending_approvals"] >= 0

    def test_agent_runs_scoped_per_tenant(self, client, setup_tenants):
        """Run de agente do tenant A não aparece na listagem do tenant B."""
        resp = client.get("/automation/agents", headers=setup_tenants["tenant_a"]["headers"])
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        assert agents, "agentes default devem existir"
        agent_id = agents[0]["id"]

        resp = client.post(
            f"/automation/agents/{agent_id}/execute",
            json={"goal": "isolamento cross-tenant"},
            headers=setup_tenants["tenant_a"]["headers"],
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        resp = client.get("/automation/agents/runs", headers=setup_tenants["tenant_b"]["headers"])
        assert resp.status_code == 200
        ids_b = [r["id"] for r in resp.json()["runs"]]
        assert run_id not in ids_b

        resp = client.get("/automation/agents/runs", headers=setup_tenants["tenant_a"]["headers"])
        assert resp.status_code == 200
        ids_a = [r["id"] for r in resp.json()["runs"]]
        assert run_id in ids_a

        # Stop de run de outro tenant → 400 (não pausa o run alheio).
        resp = client.post(
            f"/automation/agents/runs/{run_id}/stop",
            headers=setup_tenants["tenant_b"]["headers"],
        )
        assert resp.status_code == 400


class TestApprovalEngineTenantScope:
    """Semântica de dono da fila de aprovações (memória e Redis)."""

    def test_approve_reject_wrong_tenant_as_missing(self):
        from app.domain.automation.policy import ApprovalEngine

        engine = ApprovalEngine()
        approval = engine.create_approval(
            action="add_stock",
            arguments={"product_codigo": "001", "quantity": 10},
            actor="workflow:x",
            risk_level="HIGH",
            tenant_id="tenant_a",
        )

        # Listagem por tenant: B não vê a aprovação de A.
        assert engine.get_pending(tenant_id="tenant_a")[0].id == approval.id
        assert engine.get_pending(tenant_id="tenant_b") == []
        assert [a.id for a in engine.get_all(tenant_id="tenant_b")] == []

        # Dono errado: tratada como inexistente (sem vazar existência).
        assert engine.approve(approval.id, "admin_b", tenant_id="tenant_b") is False
        assert engine.reject(approval.id, tenant_id="tenant_b") is False
        assert engine.get(approval.id).status.value == "PENDING"

        # Dono certo: aprova normalmente.
        assert engine.approve(approval.id, "admin_a", tenant_id="tenant_a") is True

    def test_kill_switch_scoped(self):
        from app.domain.automation.policy import PolicyEngine
        from app.application.automation.automations import register_default_policies

        engine = PolicyEngine()
        register_default_policies(engine)
        engine.activate_kill_switch("tenant_a")
        assert engine.is_kill_switch_active("tenant_a") is True
        assert engine.is_kill_switch_active("tenant_b") is False

        blocked = engine.check_permission("get_customer", "OPERATOR", tenant_id="tenant_a")
        assert not blocked["allowed"]
        allowed = engine.check_permission("get_customer", "OPERATOR", tenant_id="tenant_b")
        assert allowed["allowed"]

    def test_redis_approval_engine_serializes_tenant(self):
        from app.core.approval_redis import RedisApprovalEngine, _serialize, _deserialize
        from app.domain.automation.policy import Approval

        approval = Approval(action="send_whatsapp", tenant_id="tenant_a")
        raw = _serialize(approval)
        restored = _deserialize(raw)
        assert restored is not None
        assert restored.tenant_id == "tenant_a"

        # Interface compatível com a fila em memória.
        engine = RedisApprovalEngine(client=_FakeRedis())
        created = engine.create_approval(action="send_whatsapp", arguments={}, actor="w", tenant_id="tenant_a")
        assert created.tenant_id == "tenant_a"
        assert engine.get_pending(tenant_id="tenant_a")
        assert engine.get_pending(tenant_id="tenant_b") == []
        assert engine.approve(created.id, "op", tenant_id="tenant_b") is False
        assert engine.approve(created.id, "op", tenant_id="tenant_a") is True


class _FakeRedis:
    """Redis mínimo para testar a lógica de índice por tenant sem servidor."""

    def __init__(self):
        self.store = {}
        self.ttls = {}

    def set(self, key, value, ex=None):
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex

    def get(self, key):
        return self.store.get(key)

    def zadd(self, key, mapping):
        zset = self.store.setdefault(key, {})
        zset.update(mapping)

    def zrange(self, key, start, end):
        zset = self.store.get(key, {})
        return sorted(zset.keys(), key=lambda k: zset[k])

    def zremrangebyscore(self, key, min_score, max_score):
        zset = self.store.get(key, {})
        for k in list(zset.keys()):
            if zset[k] <= max_score:
                del zset[k]

    def expire(self, key, ttl):
        self.ttls[key] = ttl

    def ping(self):
        return True
