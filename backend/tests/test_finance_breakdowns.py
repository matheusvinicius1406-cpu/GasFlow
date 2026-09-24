"""P1 — Central Financeira: backend aditivo (params de lista + breakdowns + aging).

Cobre o PR P1 do plano da Fase 2:
- params aditivos `q`, `date_from`, `date_to`, `order_by`, `order` nas 4
  listagens (defaults = comportamento atual; order_by inválido → 400);
- GET /finance/reports/categories (despesas ATIVAS por categoria);
- GET /finance/reports/methods (pagamentos recebidos por forma);
- GET /finance/receivables/summary (aging 0-30/31-60/61-90/90+);
- recorte por tenant em todos eles.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.database.init_db import engine
from app.infrastructure.repositories.financial_models import (
    ExpenseModel,
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


# ── Auth ─────────────────────────────────────────────


def test_novos_endpoints_exigem_auth(client):
    for path in (
        "/finance/reports/categories",
        "/finance/reports/methods",
        "/finance/receivables/summary",
    ):
        assert client.get(path).status_code in (401, 403), path


# ── Categories ───────────────────────────────────────


class TestCategories:
    def test_agrupa_despesas_ativas_por_categoria(self, client, admin_token):
        janela = datetime(2026, 6, 10, 12, 0)
        _insert(
            ExpenseModel,
            tenant_id="default",
            description="gasolina",
            amount=Decimal("300.00"),
            category="FUEL",
            date=janela,
            status="ACTIVE",
        )
        _insert(
            ExpenseModel,
            tenant_id="default",
            description="óleo",
            amount=Decimal("100.00"),
            category="FUEL",
            date=janela,
            status="ACTIVE",
        )
        _insert(
            ExpenseModel,
            tenant_id="default",
            description="cancelada",
            amount=Decimal("999.00"),
            category="FUEL",
            date=janela,
            status="CANCELLED",
        )
        _insert(
            ExpenseModel,
            tenant_id="outro-tenant",
            description="vaza",
            amount=Decimal("888.00"),
            category="FUEL",
            date=janela,
            status="ACTIVE",
        )

        res = client.get(
            "/finance/reports/categories",
            params={"from": "2026-06-10", "to": "2026-06-10"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["from"] == "2026-06-10"
        assert body["to"] == "2026-06-10"
        assert body["days"] == 1
        assert Decimal(body["total"]) == Decimal("400.00")
        assert len(body["items"]) == 1
        assert body["items"][0]["category"] == "FUEL"
        assert Decimal(body["items"][0]["total"]) == Decimal("400.00")
        assert body["items"][0]["pct"] == 100.0

    def test_from_sem_to_e_rejeitado(self, client, admin_token):
        res = client.get(
            "/finance/reports/categories",
            params={"from": "2026-06-01"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 400

    def test_dias_invalidos_continuam_aceitos_no_periodo_livre(self, client, admin_token):
        """/reports/categories aceita days ge=1 le=365 (diferente dos relatórios de entrega)."""
        res = client.get("/finance/reports/categories", params={"days": 15}, headers=_auth(admin_token))
        assert res.status_code == 200, res.text


# ── Methods ──────────────────────────────────────────


class TestMethods:
    def test_agrupa_pagamentos_recebidos_por_forma(self, client, admin_token):
        janela = datetime(2026, 6, 15, 10, 0)
        _insert(
            PaymentModel,
            tenant_id="default",
            order_codigo="M-PIX-1",
            amount=Decimal("70.00"),
            method="PIX",
            status="PAID",
            paid_at=janela,
            created_at=janela,
        )
        _insert(
            PaymentModel,
            tenant_id="default",
            order_codigo="M-CASH-1",
            amount=Decimal("20.00"),
            method="CASH",
            status="PAID",
            paid_at=janela,
            created_at=janela,
        )
        _insert(
            PaymentModel,
            tenant_id="default",
            order_codigo="M-REF-1",
            amount=Decimal("999.00"),
            method="PIX",
            status="REFUNDED",
            paid_at=janela,
            created_at=janela,
        )
        _insert(
            PaymentModel,
            tenant_id="outro-tenant",
            order_codigo="M-VAZA-1",
            amount=Decimal("888.00"),
            method="PIX",
            status="PAID",
            paid_at=janela,
            created_at=janela,
        )

        res = client.get(
            "/finance/reports/methods",
            params={"from": "2026-06-15", "to": "2026-06-15"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert Decimal(body["total"]) == Decimal("90.00")
        by_method = {i["method"]: Decimal(i["total"]) for i in body["items"]}
        assert by_method == {"PIX": Decimal("70.00"), "CASH": Decimal("20.00")}
        assert body["items"][0]["method"] == "PIX"  # maior primeiro
        assert body["items"][0]["pct"] == pytest.approx(77.8)


# ── Receivables summary (aging) ─────────────────────


class TestReceivablesSummary:
    def test_buckets_por_dias_de_atraso(self, client, admin_token):
        hoje = datetime.utcnow()
        _insert(
            ReceivableModel,
            tenant_id="default",
            customer_codigo="AGE-1",
            order_codigo="AGE-O-1",
            original_amount=Decimal("100.00"),
            paid_amount=Decimal("0.00"),
            due_date=hoje + timedelta(days=10),  # não vencido → 0-30
            status="OPEN",
        )
        _insert(
            ReceivableModel,
            tenant_id="default",
            customer_codigo="AGE-2",
            order_codigo="AGE-O-2",
            original_amount=Decimal("200.00"),
            paid_amount=Decimal("50.00"),
            due_date=hoje - timedelta(days=45),  # 45 dias → 31-60
            status="OVERDUE",
        )
        _insert(
            ReceivableModel,
            tenant_id="default",
            customer_codigo="AGE-3",
            order_codigo="AGE-O-3",
            original_amount=Decimal("300.00"),
            paid_amount=Decimal("0.00"),
            due_date=hoje - timedelta(days=120),  # 120 dias → 90+
            status="OVERDUE",
        )
        _insert(
            ReceivableModel,
            tenant_id="outro-tenant",
            customer_codigo="AGE-X",
            order_codigo="AGE-O-X",
            original_amount=Decimal("999.00"),
            paid_amount=Decimal("0.00"),
            due_date=hoje - timedelta(days=45),
            status="OVERDUE",
        )

        res = client.get("/finance/receivables/summary", headers=_auth(admin_token))
        assert res.status_code == 200, res.text
        body = res.json()

        assert body["open_count"] == 3
        assert Decimal(body["open_total"]) == Decimal("550.00")  # 100 + 150 + 300
        assert body["overdue_count"] == 2
        assert Decimal(body["overdue_total"]) == Decimal("450.00")

        buckets = {b["bucket"]: b for b in body["buckets"]}
        assert set(buckets) == {"0-30", "31-60", "61-90", "90+"}
        assert buckets["0-30"]["count"] == 1
        assert Decimal(buckets["0-30"]["total"]) == Decimal("100.00")
        assert buckets["31-60"]["count"] == 1
        assert Decimal(buckets["31-60"]["total"]) == Decimal("150.00")
        assert buckets["61-90"]["count"] == 0
        assert buckets["90+"]["count"] == 1
        assert Decimal(buckets["90+"]["total"]) == Decimal("300.00")

    def test_formato_completo_com_buckets_sempre_presentes(self, client, admin_token):
        """Mesmo com dados de outros testes no módulo, os 4 buckets sempre voltam."""
        res = client.get("/finance/receivables/summary", headers=_auth(admin_token))
        assert res.status_code == 200
        body = res.json()
        assert {"open_count", "open_total", "overdue_count", "overdue_total", "buckets"} <= set(body)
        assert [b["bucket"] for b in body["buckets"]] == ["0-30", "31-60", "61-90", "90+"]


# ── Params aditivos nas listagens ───────────────────


class TestListaParamsAditivos:
    def test_q_filtra_expenses_por_description(self, client, admin_token):
        _insert(
            ExpenseModel,
            tenant_id="default",
            description="filtro-abcxyz combustivel",
            amount=Decimal("11.00"),
            category="FUEL",
            date=datetime(2026, 7, 1, 9, 0),
            status="ACTIVE",
        )
        _insert(
            ExpenseModel,
            tenant_id="default",
            description="outra despesa qualquer",
            amount=Decimal("22.00"),
            category="OTHER",
            date=datetime(2026, 7, 2, 9, 0),
            status="ACTIVE",
        )

        res = client.get("/finance/expenses", params={"q": "abcxyz"}, headers=_auth(admin_token))
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total"] == 1
        assert "abcxyz" in body["items"][0]["description"]

    def test_date_range_filtrando_expenses(self, client, admin_token):
        res = client.get(
            "/finance/expenses",
            params={"date_from": "2026-07-02", "date_to": "2026-07-02"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total"] >= 1
        for item in body["items"]:
            assert item["date"].startswith("2026-07-02")

    def test_order_by_e_order_asc(self, client, admin_token):
        res = client.get(
            "/finance/expenses",
            params={"order_by": "amount", "order": "asc"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        amounts = [float(i["amount"]) for i in res.json()["items"]]
        assert amounts == sorted(amounts)

    def test_order_by_invalido_retorna_400(self, client, admin_token):
        res = client.get(
            "/finance/expenses",
            params={"order_by": "sql_injection"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 400
        assert "order_by" in res.json()["detail"]

    def test_order_invalido_retorna_400(self, client, admin_token):
        res = client.get("/finance/cash", params={"order": "sideways"}, headers=_auth(admin_token))
        assert res.status_code == 400

    def test_date_from_invalida_retorna_400(self, client, admin_token):
        res = client.get("/finance/payments", params={"date_from": "01/07/2026"}, headers=_auth(admin_token))
        assert res.status_code == 400

    @pytest.mark.parametrize(
        "path,param",
        [
            ("/finance/payments", "status"),
            ("/finance/expenses", "status"),
            ("/finance/cash", "type_filter"),
        ],
    )
    def test_enum_invalido_retorna_400_nao_500(self, client, admin_token, path, param):
        """Enum de query inválido é erro do cliente (400), nunca ValueError cru (500)."""
        res = client.get(path, params={param: "NAO_EXISTE"}, headers=_auth(admin_token))
        assert res.status_code == 400, res.text
        assert param in res.json()["detail"]

    def test_update_overdue_status_respeita_tenant(self):
        """O UPDATE de vencimento não pode alcançar recebíveis de outro tenant."""
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from app.infrastructure.repositories.financial_repositories import (
            SQLAlchemyReceivableRepository,
        )

        hoje = datetime.utcnow()
        outro_id = _insert(
            ReceivableModel,
            tenant_id="outro-tenant",
            customer_codigo="ODUE-1",
            order_codigo="ODUE-O-1",
            original_amount=Decimal("77.00"),
            paid_amount=Decimal("0.00"),
            due_date=hoje - timedelta(days=5),
            status="OPEN",
        )
        try:
            db = Session(bind=engine)
            try:
                count = SQLAlchemyReceivableRepository(db, "default").update_overdue_status(hoje)
                assert count >= 0
                row = db.execute(select(ReceivableModel).where(ReceivableModel.id == outro_id)).scalar_one()
                assert row.status == "OPEN", "update_overdue_status vazou para outro tenant"
            finally:
                db.close()
        finally:
            db = Session(bind=engine)
            try:
                db.query(ReceivableModel).filter(ReceivableModel.id == outro_id).delete()
                db.commit()
            finally:
                db.close()

    def test_defaults_preservam_comportamento(self, client, admin_token):
        """Sem params novos, as listagens continuam 200 com a forma antiga."""
        for path in ("/finance/payments", "/finance/expenses", "/finance/receivables", "/finance/cash"):
            res = client.get(path, headers=_auth(admin_token))
            assert res.status_code == 200, path
            body = res.json()
            assert {"items", "total", "page", "page_size", "total_pages"} <= set(body)

    def test_payments_q_busca_em_order_codigo(self, client, admin_token):
        _insert(
            PaymentModel,
            tenant_id="default",
            order_codigo="QPAY-UNIQUE-42",
            amount=Decimal("5.00"),
            method="CASH",
            status="PAID",
            paid_at=datetime(2026, 7, 3, 8, 0),
            created_at=datetime(2026, 7, 3, 8, 0),
        )
        res = client.get("/finance/payments", params={"q": "QPAY-UNIQUE-42"}, headers=_auth(admin_token))
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total"] == 1
        assert body["items"][0]["order_codigo"] == "QPAY-UNIQUE-42"

    def test_receivables_order_by_due_date_desc(self, client, admin_token):
        res = client.get(
            "/finance/receivables",
            params={"order_by": "due_date", "order": "desc"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        dues = [i["due_date"] for i in res.json()["items"] if i["due_date"]]
        assert dues == sorted(dues, reverse=True)
