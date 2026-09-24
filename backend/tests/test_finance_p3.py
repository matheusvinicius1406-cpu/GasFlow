"""P3 — Central Financeira: orçamento, relatórios salvos, auditoria e finance.write.

Cobre o PR P3 do plano da Fase 2:
- GET|PUT /finance/budget (V4: tenant+ano+mês+categoria; replace-all);
- GET|POST/DELETE /finance/saved-reports (limite 100, nome único por tenant);
- escrita em auth_audit_log nas mutações financeiras (payment, expense,
  budget, saved_report — inclusive o cancel do PSP em payments.py) +
  GET /finance/audit (leitura exige audit.view; janela `days`);
- RBAC: finance.write no catálogo, em OPERATOR e NÃO em VIEWER.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.database.init_db import engine
from app.infrastructure.repositories.auth_model import AuthAuditModel
from app.infrastructure.repositories.financial_models import (
    CashMovementModel,
    ExpenseModel,
    FinanceBudgetModel,
    FinanceSavedReportModel,
    FinancialLedgerModel,
    PaymentModel,
    ReceivableModel,
)
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


def _insert(model, **fields):
    from sqlalchemy.orm import Session

    db = Session(bind=engine)
    try:
        row = model(**fields)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def _create_user_with_role(client, admin_headers, role: str) -> str:
    """Cria usuário com `role`, troca a senha e devolve o token."""
    username = f"p3_{role.lower()}_{uuid.uuid4().hex[:6]}"
    res = client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": username,
            "email": f"{username}@gasflow.local",
            "password": "InitialPass1!",
            "role": role,
        },
    )
    assert res.status_code == 201, res.text

    login = client.post("/auth/login", json={"username": username, "password": "InitialPass1!"})
    assert login.status_code == 200, login.text
    token = login.json()["token"]

    # Usuário nasce com must_change_password=True — troca antes de exercitar
    # permissões (senão o 403 vem do bloqueio de senha, não do RBAC).
    changed = client.post(
        "/auth/change-password",
        headers=_auth(token),
        json={"current_password": "InitialPass1!", "new_password": "P3Passw0rd!"},
    )
    assert changed.status_code == 200, changed.text
    return token


def _audit_items(client, token: str, **params) -> list[dict]:
    res = client.get("/finance/audit", params={"days": 30, **params}, headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()["items"]


@pytest.fixture(scope="module", autouse=True)
def _cleanup_p3_rows():
    """Sai do módulo sem deixar rastro para os módulos de teste seguintes."""
    yield
    from sqlalchemy import or_
    from sqlalchemy.orm import Session

    from app.infrastructure.repositories.payment_model import PaymentServiceRecord

    db = Session(bind=engine)
    try:
        db.query(FinanceBudgetModel).delete(synchronize_session=False)
        db.query(FinanceSavedReportModel).delete(synchronize_session=False)
        db.query(ExpenseModel).filter(ExpenseModel.description.like("despesa P3%")).delete(synchronize_session=False)
        db.query(PaymentModel).filter(PaymentModel.order_codigo.like("P3-%")).delete(synchronize_session=False)
        db.query(ReceivableModel).filter(ReceivableModel.order_codigo.like("P3-%")).delete(synchronize_session=False)
        db.query(CashMovementModel).filter(
            or_(
                CashMovementModel.description.like("%P3-REC%"),
                CashMovementModel.description.like("%despesa P3%"),
            )
        ).delete(synchronize_session=False)
        db.query(FinancialLedgerModel).filter(
            or_(
                FinancialLedgerModel.description.like("%P3-REC%"),
                FinancialLedgerModel.description.like("%despesa P3%"),
            )
        ).delete(synchronize_session=False)
        db.query(PaymentServiceRecord).filter(PaymentServiceRecord.order_id.like("P3-%")).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


# ── Auth ─────────────────────────────────────────────


def test_novos_endpoints_exigem_auth(client):
    cases = (
        ("GET", "/finance/budget", None),
        ("PUT", "/finance/budget", {"year": 2031, "month": 5, "items": []}),
        ("GET", "/finance/saved-reports", None),
        ("POST", "/finance/saved-reports", {"name": "x", "report_type": "dre"}),
        ("DELETE", "/finance/saved-reports/1", None),
        ("GET", "/finance/audit", None),
    )
    for method, path, body in cases:
        res = client.request(method, path, json=body)
        assert res.status_code in (401, 403), f"{method} {path} → {res.status_code}"


# ── Budget ───────────────────────────────────────────


class TestBudget:
    def test_get_default_mes_corrente(self, client, admin_token):
        res = client.get("/finance/budget", headers=_auth(admin_token))
        assert res.status_code == 200, res.text
        body = res.json()
        agora = datetime.utcnow()
        assert body["year"] == agora.year
        assert body["month"] == agora.month
        assert body["items"] == []
        assert Decimal(body["total"]) == Decimal("0.00")

    def test_put_get_roundtrip_e_total(self, client, admin_token):
        payload = {
            "year": 2031,
            "month": 5,
            "items": [
                {"category": "FUEL", "amount": "1500.50"},
                {"category": "SALARY", "amount": "8000.00"},
            ],
        }
        res = client.put("/finance/budget", json=payload, headers=_auth(admin_token))
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["year"] == 2031
        assert body["month"] == 5
        assert Decimal(body["total"]) == Decimal("9500.50")
        assert {i["category"] for i in body["items"]} == {"FUEL", "SALARY"}

        res = client.get("/finance/budget", params={"year": 2031, "month": 5}, headers=_auth(admin_token))
        assert res.status_code == 200
        got = res.json()
        assert len(got["items"]) == 2
        assert Decimal(got["total"]) == Decimal("9500.50")

    def test_put_substitui_o_mes_inteiro(self, client, admin_token):
        client.put(
            "/finance/budget",
            json={
                "year": 2032,
                "month": 1,
                "items": [
                    {"category": "FUEL", "amount": "10.00"},
                    {"category": "TAX", "amount": "20.00"},
                ],
            },
            headers=_auth(admin_token),
        )
        res = client.put(
            "/finance/budget",
            json={"year": 2032, "month": 1, "items": [{"category": "TAX", "amount": "99.00"}]},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        assert len(res.json()["items"]) == 1

        res = client.get("/finance/budget", params={"year": 2032, "month": 1}, headers=_auth(admin_token))
        items = res.json()["items"]
        assert [i["category"] for i in items] == ["TAX"]
        assert Decimal(items[0]["amount"]) == Decimal("99.00")

    def test_validacoes_rejeitadas(self, client, admin_token):
        bad_payloads = (
            ({"year": 2031, "month": 13, "items": []}, 422, "mês 13"),
            ({"year": 1999, "month": 5, "items": []}, 422, "ano fora da faixa"),
            ({"year": 2031, "month": 5, "items": [{"category": "X", "amount": "-1"}]}, 422, "valor negativo"),
            (
                {
                    "year": 2031,
                    "month": 5,
                    "items": [
                        {"category": "FUEL", "amount": "10.00"},
                        {"category": "fuel", "amount": "20.00"},
                    ],
                },
                400,
                "categoria duplicada (case-insensitive)",
            ),
            ({"year": 2031, "month": 5, "items": [{"category": "   ", "amount": "1.00"}]}, 400, "categoria vazia"),
        )
        for payload, expected, label in bad_payloads:
            res = client.put("/finance/budget", json=payload, headers=_auth(admin_token))
            assert res.status_code == expected, f"{label}: {res.status_code} {res.text}"

    def test_recorte_por_tenant(self, client, admin_token):
        _insert(
            FinanceBudgetModel,
            tenant_id="outro-tenant",
            year=2033,
            month=7,
            category="VAZA",
            amount=Decimal("999.00"),
        )
        res = client.put(
            "/finance/budget",
            json={"year": 2033, "month": 7, "items": [{"category": "FUEL", "amount": "10.00"}]},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text

        res = client.get("/finance/budget", params={"year": 2033, "month": 7}, headers=_auth(admin_token))
        items = res.json()["items"]
        assert [i["category"] for i in items] == ["FUEL"]


# ── Saved reports ────────────────────────────────────


class TestSavedReports:
    def test_crud(self, client, admin_token):
        res = client.post(
            "/finance/saved-reports",
            json={"name": "DRE do mês P3", "report_type": "dre", "params": {"days": 30}},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["name"] == "DRE do mês P3"
        assert body["report_type"] == "dre"
        assert body["params"] == {"days": 30}
        report_id = body["id"]

        res = client.get("/finance/saved-reports", headers=_auth(admin_token))
        assert res.status_code == 200
        listing = res.json()
        assert listing["total"] >= 1
        assert "DRE do mês P3" in [i["name"] for i in listing["items"]]

        res = client.delete(f"/finance/saved-reports/{report_id}", headers=_auth(admin_token))
        assert res.status_code == 200, res.text

        res = client.get("/finance/saved-reports", headers=_auth(admin_token))
        assert "DRE do mês P3" not in [i["name"] for i in res.json()["items"]]

    def test_nome_duplicado_no_tenant_rejeitado(self, client, admin_token):
        payload = {"name": "Duplicado P3", "report_type": "period"}
        res = client.post("/finance/saved-reports", json=payload, headers=_auth(admin_token))
        assert res.status_code == 200, res.text
        res = client.post("/finance/saved-reports", json=payload, headers=_auth(admin_token))
        assert res.status_code == 400, res.text

    def test_delete_inexistente_404(self, client, admin_token):
        res = client.delete("/finance/saved-reports/999999", headers=_auth(admin_token))
        assert res.status_code == 404

    def test_nome_em_branco_rejeitado(self, client, admin_token):
        res = client.post(
            "/finance/saved-reports",
            json={"name": "   ", "report_type": "dre"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 400, res.text

    def test_recorte_por_tenant(self, client, admin_token):
        vaza_id = _insert(
            FinanceSavedReportModel,
            tenant_id="outro-tenant",
            name="Relatório vaza P3",
            report_type="dre",
        )
        res = client.get("/finance/saved-reports", headers=_auth(admin_token))
        assert "Relatório vaza P3" not in [i["name"] for i in res.json()["items"]]

        res = client.delete(f"/finance/saved-reports/{vaza_id}", headers=_auth(admin_token))
        assert res.status_code == 404


# ── Auditoria ────────────────────────────────────────


class TestAuditoria:
    def test_expense_create_cancel_audita_com_antes_depois(self, client, admin_token):
        res = client.post(
            "/finance/expenses",
            json={"description": "despesa P3 auditoria", "amount": "50.00", "category": "FUEL"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        expense_id = res.json()["expense"]["id"]

        res = client.post(f"/finance/expenses/{expense_id}/cancel", headers=_auth(admin_token))
        assert res.status_code == 200, res.text

        items = _audit_items(client, admin_token)
        expense_items = [i for i in items if i["resource"] == "expense" and i["resource_id"] == str(expense_id)]
        actions = {i["action"] for i in expense_items}
        assert actions == {"expense.created", "expense.cancelled"}

        created = next(i for i in expense_items if i["action"] == "expense.created")
        assert created["after_json"]["description"] == "despesa P3 auditoria"
        assert created["after_json"]["amount"] == "50.00"

        cancelled = next(i for i in expense_items if i["action"] == "expense.cancelled")
        assert cancelled["before_json"]["status"] == "ACTIVE"
        assert cancelled["after_json"]["status"] == "CANCELLED"

    def test_budget_put_audita_antes_depois(self, client, admin_token):
        client.put(
            "/finance/budget",
            json={"year": 2034, "month": 3, "items": [{"category": "FUEL", "amount": "100.00"}]},
            headers=_auth(admin_token),
        )
        res = client.put(
            "/finance/budget",
            json={
                "year": 2034,
                "month": 3,
                "items": [
                    {"category": "FUEL", "amount": "250.00"},
                    {"category": "TAX", "amount": "50.00"},
                ],
            },
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text

        items = _audit_items(client, admin_token, days=1)
        events = [i for i in items if i["action"] == "budget.upserted" and i["resource_id"] == "2034-03"]
        assert len(events) == 2
        # O evento mais recente tem antes=1 item e depois=2.
        ultimo = next(e for e in events if len(e["after_json"]["items"]) == 2)
        assert len(ultimo["before_json"]["items"]) == 1
        assert ultimo["before_json"]["items"][0]["amount"] == "100.00"

    def test_payment_registrado_e_estornado_audita(self, client, admin_token):
        _insert(
            ReceivableModel,
            tenant_id="default",
            customer_codigo="P3C-1",
            order_codigo="P3-REC-1",
            original_amount=Decimal("300.00"),
            paid_amount=Decimal("0.00"),
            status="OPEN",
        )
        res = client.post(
            "/finance/orders/P3-REC-1/payments",
            json={"amount": "100.00", "method": "CASH"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        payment_id = res.json()["payment"]["id"]

        # Caminho de sucesso do estorno (antes: KeyError em result["status"] → 500).
        res = client.post(
            f"/finance/payments/{payment_id}/refund",
            params={"reason": "teste P3"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "refunded"

        items = _audit_items(client, admin_token)
        payment_actions = {
            i["action"] for i in items if i["resource"] == "payment" and i["resource_id"] == str(payment_id)
        }
        assert "payment.registered" in payment_actions
        assert "payment.refunded" in payment_actions

    def test_psp_cancelamento_audita(self, client, admin_token):
        res = client.post(
            "/payments/",
            json={
                "order_id": "P3-PSP-1",
                "order_codigo": "P3PSP01",
                "customer_codigo": "000001",
                "amount": 50.0,
                "method_code": "CASH",
            },
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        psp_id = res.json()["payment"]["id"]

        res = client.post(f"/payments/{psp_id}/cancel", headers=_auth(admin_token))
        assert res.status_code == 200, res.text

        items = _audit_items(client, admin_token)
        cancelled = any(i["action"] == "payment.cancelled" and i["resource_id"] == str(psp_id) for i in items)
        assert cancelled, "cancel do PSP não gravou auth_audit_log"

    def test_janela_days_filtra_eventos_antigos(self, client, admin_token):
        _insert(
            AuthAuditModel,
            id=str(uuid.uuid4()),
            actor_id="p3-teste",
            actor_type="USER",
            tenant_id="default",
            action="payment.registered",
            resource="payment",
            resource_id="P3-EVENTO-ANTIGO",
            result="SUCCESS",
            timestamp=datetime.utcnow() - timedelta(days=40),
            ip_address="",
            user_agent="",
            platform="web",
        )
        ids_30 = [i["resource_id"] for i in _audit_items(client, admin_token, days=30)]
        assert "P3-EVENTO-ANTIGO" not in ids_30

        ids_60 = [i["resource_id"] for i in _audit_items(client, admin_token, days=60)]
        assert "P3-EVENTO-ANTIGO" in ids_60

    def test_leitura_exige_audit_view(self, client, admin_token):
        admin_headers = _auth(admin_token)
        operator_token = _create_user_with_role(client, admin_headers, "OPERATOR")
        res = client.get("/finance/audit", headers=_auth(operator_token))
        assert res.status_code == 403
        assert "audit.view" in res.text

        viewer_token = _create_user_with_role(client, admin_headers, "VIEWER")
        res = client.get("/finance/audit", headers=_auth(viewer_token))
        assert res.status_code == 403

        # O próprio admin (admin.*) continua lendo.
        res = client.get("/finance/audit", headers=admin_headers)
        assert res.status_code == 200

    def test_recorte_por_tenant(self, client, admin_token):
        _insert(
            AuthAuditModel,
            id=str(uuid.uuid4()),
            actor_id="p3-teste",
            actor_type="USER",
            tenant_id="outro-tenant",
            action="payment.registered",
            resource="payment",
            resource_id="P3-EVENTO-OUTRO-TENANT",
            result="SUCCESS",
            timestamp=datetime.utcnow(),
            ip_address="",
            user_agent="",
            platform="web",
        )
        ids = [i["resource_id"] for i in _audit_items(client, admin_token, days=1)]
        assert "P3-EVENTO-OUTRO-TENANT" not in ids


# ── RBAC finance.write (V3) ──────────────────────────


class TestRbacFinanceWrite:
    def test_no_catalogo_e_nas_matrizes(self):
        from app.domain.security.models import DEFAULT_PERMISSIONS, ROLE_PERMISSIONS, SystemRole
        from app.infrastructure.database.rbac_seed import PERMISSIONS, ROLE_MATRIX

        codes = [code for code, _module, _desc in PERMISSIONS]
        assert "finance.write" in codes

        # OPERATOR pode escrever; VIEWER não (MANAGER cobre por finance.*).
        assert "finance.write" in ROLE_MATRIX["OPERATOR"]
        assert "finance.write" not in ROLE_MATRIX["VIEWER"]
        assert "finance.*" in ROLE_MATRIX["MANAGER"]

        # Fallback de código espelha a matriz (loader usa o dict sem catálogo).
        assert "finance.write" in ROLE_PERMISSIONS[SystemRole.OPERATOR]
        assert "finance.write" not in ROLE_PERMISSIONS.get(SystemRole.VIEWER, [])

        assert ("finance", "write") in DEFAULT_PERMISSIONS

    def test_operator_recebe_e_viewer_nao(self, client, admin_token):
        admin_headers = _auth(admin_token)

        operator_token = _create_user_with_role(client, admin_headers, "OPERATOR")
        res = client.get("/auth/me", headers=_auth(operator_token))
        assert res.status_code == 200
        assert "finance.write" in res.json()["permissions"]

        viewer_token = _create_user_with_role(client, admin_headers, "VIEWER")
        res = client.get("/auth/me", headers=_auth(viewer_token))
        assert res.status_code == 200
        perms = res.json()["permissions"]
        assert "finance.write" not in perms
        assert "finance.read" in perms  # VIEWER continua lendo
