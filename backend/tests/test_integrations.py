"""
Integration Module Tests — sites de revendas + agente de ancoragem.

Cobre: CRUD de integrações (RBAC), webhook /import com token por integração,
sync-run com criação automática de cliente/produto + pedido real, dedupe,
reprocess, logs e teste de conexão contra um servidor HTTP local (fixture).
"""

import http.server
import threading

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.application.integrations.import_service import (
    IntegrationImportService,
    normalize_order,
    parse_money,
)


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


# ── Servidor HTTP local (site "da revenda" de teste) ─────

ORDERS_HTML = b"""<html><head><title>Painel de Pedidos</title></head><body>
<table class="orders">
<tr><th>Pedido</th><th>Cliente</th><th>Valor</th><th>Status</th></tr>
<tr><td>1001</td><td>Maria Souza</td><td>R$ 150,00</td><td>pendente</td></tr>
</table>
</body></html>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/pedidos"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(ORDERS_HTML)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site_url():
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


# ── Parsing / normalização puros ─────────────────────────


def test_parse_money_ptbr():
    assert parse_money("R$ 1.234,56") == 1234.56
    assert parse_money("1234,56") == 1234.56
    assert parse_money("R$ 99.90") == 99.90
    assert parse_money(12.3) == 12.3
    assert parse_money("") is None
    assert parse_money(None) is None


def test_normalize_order_accepts_pt_en_and_items():
    order = normalize_order(
        {
            "numero": "1001",
            "cliente": "Maria Souza",
            "telefone": "(91) 98168-9969",
            "endereco": "Rua A, 123, Centro",
            "total": "R$ 150,00",
            "frete": "10,00",
            "itens": ["2x P13", {"produto": "P45", "quantidade": 1, "preco": "89,90"}],
        }
    )
    assert order.external_id == "1001"
    assert order.client_name == "Maria Souza"
    assert order.client_phone == "(91) 98168-9969"
    assert order.total == 150.0
    assert order.delivery_fee == 10.0
    assert len(order.items) == 2
    assert order.items[0].product_name == "P13"
    assert order.items[0].quantity == 2
    assert order.items[1].unit_price == 89.9


# ── CRUD + RBAC ──────────────────────────────────────────


def test_integration_crud_flow(client, admin_token):
    # create
    res = client.post(
        "/integrations",
        headers=_auth(admin_token),
        json={
            "name": "Site Revenda X",
            "base_url": "https://revendax.com.br",
            "orders_path": "/pedidos",
            "auth_type": "none",
            "sync_interval_minutes": 10,
        },
    )
    assert res.status_code == 201, res.text
    integ = res.json()
    assert integ["import_token"]  # token gerado
    assert integ["has_credentials"] is False

    # list
    res = client.get("/integrations", headers=_auth(admin_token))
    assert res.status_code == 200
    assert any(i["id"] == integ["id"] for i in res.json()["integrations"])

    # update
    res = client.put(
        f"/integrations/{integ['id']}",
        headers=_auth(admin_token),
        json={"sync_interval_minutes": 30, "is_active": False},
    )
    assert res.status_code == 200
    assert res.json()["sync_interval_minutes"] == 30

    # rotate token
    res = client.post(f"/integrations/{integ['id']}/rotate-token", headers=_auth(admin_token))
    assert res.status_code == 200
    new_token = res.json()["import_token"]
    assert new_token != integ["import_token"]

    # soft delete
    res = client.delete(f"/integrations/{integ['id']}", headers=_auth(admin_token))
    assert res.status_code == 200
    assert res.json()["is_active"] is False


def test_integration_requires_permission(client, admin_token):
    # sem token → 401/403
    res = client.get("/integrations")
    assert res.status_code in (401, 403)


# ── Webhook /import com token ────────────────────────────


def _mk_integration(client, admin_token, name="Webhook Site"):
    res = client.post(
        "/integrations",
        headers=_auth(admin_token),
        json={"name": name, "base_url": "https://revenda.com", "sync_interval_minutes": 5},
    )
    assert res.status_code == 201
    return res.json()


def test_import_rejects_invalid_token(client, admin_token):
    integ = _mk_integration(client, admin_token)
    res = client.post(
        "/integrations/import",
        json={"integration_id": integ["id"], "order": {"external_id": "X1", "items": [{"nome": "P13"}]}},
        headers={"X-Integration-Token": "wrong-token"},
    )
    assert res.status_code == 401


def test_import_creates_order_end_to_end(client, admin_token):
    """E2E: pedido normalizado → cliente criado → produto criado → pedido no GasFlow."""
    integ = _mk_integration(client, admin_token, "E2E Site")
    payload = {
        "external_id": f"E2E-{id(integ)}-1",
        "cliente": "João Importado",
        "telefone": "91991234567",
        "endereco": "Rua Teste, 100, Centro",
        "total": "R$ 120,00",
        "frete": "R$ 10,00",
        "pagamento": "PIX",
        "itens": [{"produto": "Botijão P13 Import", "quantidade": 1, "preco": "110,00"}],
    }
    res = client.post(
        "/integrations/import",
        json={"integration_id": integ["id"], "order": payload},
        headers={"X-Integration-Token": integ["import_token"]},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "success", body.get("error_message")
    assert body["gasflow_order_codigo"]

    # pedido real existe e tem o item
    order_codigo = body["gasflow_order_codigo"]
    res = client.get(f"/orders/{order_codigo}", headers=_auth(admin_token))
    assert res.status_code == 200, res.text
    order = res.json()
    assert order["client_codigo"]
    assert order["source"] == "INTEGRATION" if "source" in order else True

    # dedupe: mesmo external_id → não duplica
    res = client.post(
        "/integrations/import",
        json={"integration_id": integ["id"], "order": payload},
        headers={"X-Integration-Token": integ["import_token"]},
    )
    assert res.status_code == 201
    assert res.json()["status"] in ("success", "error")  # dedupe não cria segundo pedido
    res2 = client.get(f"/integrations/{integ['id']}/orders", headers=_auth(admin_token))
    external_ids = [o["external_id"] for o in res2.json()["orders"]]
    assert external_ids.count(payload["external_id"]) == 1


def test_sync_run_batch_and_logs(client, admin_token):
    integ = _mk_integration(client, admin_token, "Batch Site")
    orders = [
        {
            "external_id": f"B{i}",
            "cliente": f"Cliente B{i}",
            "telefone": f"919900000{i}",
            "itens": [{"produto": f"Produto B{i}", "quantidade": 1}],
        }
        for i in range(3)
    ]
    orders.append({"external_id": "B-err", "itens": []})  # sem itens → erro controlado

    res = client.post(
        f"/integrations/{integ['id']}/sync-run",
        headers=_auth(admin_token),
        json={"orders": orders, "errors": [{"external_ref": "Z9", "message": "parse falhou"}], "trigger": "agent"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["total_found"] == 5  # 4 extraídos + 1 erro do agente
    assert body["total_imported"] == 3
    assert body["total_errors"] == 2  # 1 import sem itens + 1 do agente
    assert body["status"] == "partial"

    # logs registrados
    res = client.get(f"/integrations/{integ['id']}/logs", headers=_auth(admin_token))
    assert res.status_code == 200
    logs = res.json()["logs"]
    assert len(logs) >= 1
    assert logs[0]["status"] == "partial"

    # status da integração atualizado
    res = client.get(f"/integrations/{integ['id']}", headers=_auth(admin_token))
    assert res.json()["last_sync_status"] == "partial"


def test_reprocess_error_order(client, admin_token):
    integ = _mk_integration(client, admin_token, "Reprocess Site")
    # pedido sem itens → erro; depois reprocessa corrigido
    bad = {"external_id": "R1", "cliente": "Repro Client", "itens": []}
    res = client.post(
        "/integrations/import",
        json={"integration_id": integ["id"], "order": bad},
        headers={"X-Integration-Token": integ["import_token"]},
    )
    assert res.status_code == 201
    imported_id = res.json()["imported_order_id"]
    assert res.json()["status"] == "error"

    # atualiza o external_data com itens e reprocessa
    res = client.get(f"/integrations/{integ['id']}/orders/{imported_id}", headers=_auth(admin_token))
    assert res.status_code == 200

    svc_data = {"external_id": "R1", "cliente": "Repro Client", "itens": [{"produto": "Item Repro", "quantidade": 2}]}
    from app.infrastructure.database.connection import SessionLocal

    from app.infrastructure.repositories.integration_model import ImportedOrderModel

    db = SessionLocal()
    try:
        row = db.query(ImportedOrderModel).filter(ImportedOrderModel.id == imported_id).first()
        row.external_data = svc_data
        db.commit()
    finally:
        db.close()

    res = client.post(f"/integrations/{integ['id']}/orders/{imported_id}/reprocess", headers=_auth(admin_token))
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "success", res.json().get("error_message")


# ── Test-connection contra site local ────────────────────


def test_test_connection_finds_order_table(client, admin_token, site_url):
    integ = _mk_integration(client, admin_token, "Site Local")
    res = client.put(
        f"/integrations/{integ['id']}",
        headers=_auth(admin_token),
        json={"base_url": site_url, "orders_path": "/pedidos"},
    )
    assert res.status_code == 200

    res = client.post(f"/integrations/{integ['id']}/test-connection", headers=_auth(admin_token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["page_title"] == "Painel de Pedidos"
    assert body["detection"] == "candidate"
    assert any("Cliente" in row for row in body["order_table_candidates"])


def test_test_connection_unreachable(client, admin_token):
    integ = _mk_integration(client, admin_token, "Site Morto")
    res = client.put(
        f"/integrations/{integ['id']}",
        headers=_auth(admin_token),
        json={"base_url": "http://127.0.0.1:1", "orders_path": "/pedidos"},
    )
    assert res.status_code == 200
    res = client.post(f"/integrations/{integ['id']}/test-connection", headers=_auth(admin_token))
    assert res.status_code == 200
    assert res.json()["ok"] is False
    assert "error" in res.json()


# ── Service unit (sync status transitions) ───────────────


def test_sync_status_transitions():
    from app.infrastructure.repositories.integration_model import IntegrationModel
    from app.infrastructure.database.init_db import engine
    from sqlalchemy.orm import Session as DBSession

    db = DBSession(bind=engine)
    created_id = None
    try:
        svc = IntegrationImportService(db=db, tenant_id="default")
        created_id = "svc-unit-test-1"
        integ = IntegrationModel(
            id=created_id,
            tenant_id="default",
            name="Unit",
            base_url="https://x.com",
            import_token="tok-unit-1",
        )
        db.add(integ)
        db.commit()

        # tudo sucesso → success
        log = svc.process_sync_run(
            integ, orders=[{"external_id": "U1", "itens": [{"produto": "Item U1"}]}], trigger="manual"
        )
        assert log.status == "success", f"{log.status}: {log.error_details}"

        # só erros → error
        log = svc.process_sync_run(integ, orders=[], agent_errors=[{"external_ref": "E1", "message": "x"}])
        assert log.status == "error"
        assert log.total_errors == 1
    finally:
        db.rollback()
        db.close()
        # limpeza das linhas criadas (shared dev DB hygiene)
        try:
            from sqlalchemy import text

            with engine.connect() as conn:
                conn.execute(text("DELETE FROM sync_logs WHERE integration_id = :i"), {"i": created_id})
                conn.execute(text("DELETE FROM imported_orders WHERE integration_id = :i"), {"i": created_id})
                conn.execute(text("DELETE FROM integrations WHERE id = :i"), {"i": created_id})
                conn.commit()
        except Exception:
            pass
