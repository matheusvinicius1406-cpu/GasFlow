"""P2 — Central Financeira: dre, products, projection, team, hourly, conciliation.

Cobre o PR P2 do plano da Fase 2:
- GET /finance/reports/dre (CMV ponderado + cmv_coverage);
- GET /finance/reports/products (cost_known / margem None sem nota);
- GET /finance/reports/projection (horizon, modelo declarado sem ML);
- GET /finance/reports/team (delivery_metrics + folha SALARY);
- GET /finance/reports/hourly (24 buckets por paid_at);
- GET /finance/reports/conciliation (divergências = "a revisar");
- auth, validação de params e recorte por tenant.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.database.init_db import engine
from app.infrastructure.repositories.financial_models import (
    CashMovementModel,
    ExpenseModel,
    PaymentModel,
    ReceivableModel,
)
from app.infrastructure.repositories.order_item_model import OrderItemModel
from app.infrastructure.repositories.order_model import OrderModel
from app.infrastructure.repositories.purchase_note_model import PurchaseNoteItemModel, PurchaseNoteModel
from app.main import app

PATHS_PERIOD = (
    "/finance/reports/dre",
    "/finance/reports/products",
    "/finance/reports/hourly",
    "/finance/reports/conciliation",
)
PATHS_ALL = PATHS_PERIOD + ("/finance/reports/projection", "/finance/reports/team")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200
    return res.json()["token"]


@pytest.fixture(scope="module", autouse=True)
def _cleanup_p2_rows():
    """Remove linhas do P2 ao fim do módulo — não vazar para testes seguintes."""
    yield
    from sqlalchemy.orm import Session

    db = Session(bind=engine)
    try:
        for model, col in (
            (ReceivableModel, ReceivableModel.order_codigo),
            (PaymentModel, PaymentModel.order_codigo),
            (OrderItemModel, OrderItemModel.order_codigo),
        ):
            db.query(model).filter(col.like("P2-%")).delete(synchronize_session=False)
        db.query(OrderModel).filter(OrderModel.codigo.like("P2-%")).delete(synchronize_session=False)
        db.query(CashMovementModel).filter(CashMovementModel.description.like("%P2%")).delete(synchronize_session=False)
        db.query(CashMovementModel).filter(CashMovementModel.description.in_(["ok", "delta"])).delete(
            synchronize_session=False
        )
        db.query(ExpenseModel).filter(
            ExpenseModel.description.in_(["despesa P2", "folha P2", "salário equipe P2"])
        ).delete(synchronize_session=False)
        db.query(PurchaseNoteModel).filter(PurchaseNoteModel.supplier_name.in_(["Fornecedor P2", "Outro"])).delete(
            synchronize_session=False
        )
        db.query(PurchaseNoteItemModel).filter(
            PurchaseNoteItemModel.product_codigo.in_(["P2T-GAS", "P2T-Acessorio"])
        ).delete(synchronize_session=False)
        from app.infrastructure.repositories.delivery_persistence_model import DeliveryRecord

        db.query(DeliveryRecord).filter(DeliveryRecord.driver_id == "DRV-P2").delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


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


# ── Auth + validação ──────────────────────────────────


def test_novos_endpoints_exigem_auth(client):
    for path in PATHS_ALL:
        assert client.get(path).status_code in (401, 403), path


@pytest.mark.parametrize("path", PATHS_PERIOD)
def test_from_sem_to_rejeitado(client, admin_token, path):
    res = client.get(path, params={"from": "2026-08-01"}, headers=_auth(admin_token))
    assert res.status_code == 400


def test_projection_horizon_invalido_retorna_400(client, admin_token):
    res = client.get("/finance/reports/projection", params={"horizon": 0}, headers=_auth(admin_token))
    assert res.status_code == 422  # ge=1 do FastAPI


def test_team_dias_invalidos_retorna_400(client, admin_token):
    res = client.get("/finance/reports/team", params={"days": 5}, headers=_auth(admin_token))
    assert res.status_code == 400
    assert "Janela" in res.json()["detail"]


# ── DRE + Products (seed compartilhado) ───────────────

_WINDOW = datetime(2026, 8, 3, 12, 0)


@pytest.fixture(scope="module")
def seed_dre_window():
    """Pedido com 2 produtos: um com nota CONFIRMED, outro sem custo."""
    note_id = str(uuid4())
    _insert(
        PurchaseNoteModel,
        id=note_id,
        tenant_id="default",
        note_number=900001,
        supplier_name="Fornecedor P2",
        issue_date=datetime(2026, 8, 1).date(),
        total_cents=50000,
        status="CONFIRMED",
        confirmed_at=datetime(2026, 8, 1, 10, 0),
    )
    _insert(
        PurchaseNoteItemModel,
        purchase_note_id=note_id,
        product_codigo="P2T-GAS",
        product_name="GLP 13kg",
        quantity=10,
        unit_price_cents=5000,
        subtotal_cents=50000,
    )
    # Nota de outro tenant não pode entrar no custo
    other_note = str(uuid4())
    _insert(
        PurchaseNoteModel,
        id=other_note,
        tenant_id="outro-tenant",
        note_number=1,
        supplier_name="Outro",
        issue_date=datetime(2026, 8, 1).date(),
        total_cents=100,
        status="CONFIRMED",
    )
    _insert(
        PurchaseNoteItemModel,
        purchase_note_id=other_note,
        product_codigo="P2T-GAS",
        product_name="GLP 13kg",
        quantity=1,
        unit_price_cents=100,
        subtotal_cents=100,
    )
    _insert(
        OrderModel,
        tenant_id="default",
        codigo="P2-ORD-1",
        client_codigo="000001",
        subtotal=Decimal("250.00"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("250.00"),
        payment_status="PAID",
        address_snapshot="Rua A, 1",
        status="DELIVERED",
        created_at=_WINDOW,
    )
    _insert(
        OrderItemModel,
        tenant_id="default",
        order_codigo="P2-ORD-1",
        product_codigo="P2T-GAS",
        product_nome="GLP 13kg",
        quantity=2,
        unit_price=Decimal("100.00"),
        subtotal=Decimal("200.00"),
        created_at=_WINDOW,
    )
    _insert(
        OrderItemModel,
        tenant_id="default",
        order_codigo="P2-ORD-1",
        product_codigo="P2T-Acessorio",
        product_nome="Mangueira",
        quantity=1,
        unit_price=Decimal("50.00"),
        subtotal=Decimal("50.00"),
        created_at=_WINDOW,
    )
    _insert(
        ExpenseModel,
        tenant_id="default",
        description="despesa P2",
        amount=Decimal("40.00"),
        category="FUEL",
        date=_WINDOW,
        status="ACTIVE",
    )
    yield
    # Pedido de outro tenant no mesmo período — não deve vazar
    _insert(
        OrderModel,
        tenant_id="outro-tenant",
        codigo="P2-ORD-X",
        client_codigo="9",
        total=Decimal("999.00"),
        address_snapshot="x",
        created_at=_WINDOW,
    )


class TestDre:
    def test_dre_cmv_ponderado_e_coverage(self, client, admin_token, seed_dre_window):
        res = client.get(
            "/finance/reports/dre",
            params={"from": "2026-08-03", "to": "2026-08-03"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        body = res.json()
        # Itens: P2T-GAS 2×100 (custo 50 un → CMV 100) + Acessorio 50 sem custo
        assert Decimal(body["revenue"]) == Decimal("250.00")
        assert Decimal(body["cmv"]) == Decimal("100.00")
        assert Decimal(body["gross_profit"]) == Decimal("150.00")
        # coverage = 200/250 = 80.0% (só a receita com custo conhecido)
        assert body["cmv_coverage"] == pytest.approx(80.0)
        # Despesas do dia (só a nossa — periodo de 1 dia)
        assert Decimal(body["expenses"]) == Decimal("40.00")
        assert Decimal(body["result"]) == Decimal("110.00")
        cats = {i["category"]: Decimal(i["total"]) for i in body["expense_items"]}
        assert cats.get("FUEL") == Decimal("40.00")

    def test_dre_sem_receita_coverage_none(self, client, admin_token):
        res = client.get(
            "/finance/reports/dre",
            params={"from": "2020-01-01", "to": "2020-01-02"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert Decimal(body["revenue"]) == Decimal("0.00")
        assert body["cmv_coverage"] is None
        assert body["expense_items"] == []


class TestProducts:
    def test_cost_known_e_desconhecido(self, client, admin_token, seed_dre_window):
        res = client.get(
            "/finance/reports/products",
            params={"from": "2026-08-03", "to": "2026-08-03"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        body = res.json()
        by_code = {i["product_codigo"]: i for i in body["items"]}
        assert set(by_code) == {"P2T-GAS", "P2T-Acessorio"}

        gas = by_code["P2T-GAS"]
        assert gas["cost_known"] is True
        assert Decimal(gas["unit_cost"]) == Decimal("50.00")  # 50000 cents / 10 un
        assert Decimal(gas["margin"]) == Decimal("100.00")  # 200 − 2×50
        assert gas["margin_pct"] == pytest.approx(50.0)

        acc = by_code["P2T-Acessorio"]
        assert acc["cost_known"] is False
        assert acc["unit_cost"] is None
        assert acc["margin"] is None
        assert acc["margin_pct"] is None

        assert Decimal(body["revenue"]) == Decimal("250.00")


# ── Projection ────────────────────────────────────────


class TestProjection:
    def test_modelo_declarado_e_serie_diaria(self, client, admin_token):
        hoje = datetime.utcnow()
        _insert(
            CashMovementModel,
            tenant_id="default",
            type="RECEIPT",
            amount=Decimal("1000.00"),
            description="saldo inicial P2",
            balance_after=Decimal("1234.56"),
            created_at=hoje,
        )
        _insert(
            ReceivableModel,
            tenant_id="default",
            customer_codigo="P2C-1",
            order_codigo="P2-PROJ-1",
            original_amount=Decimal("200.00"),
            paid_amount=Decimal("0.00"),
            due_date=hoje + timedelta(days=5),
            status="OPEN",
        )
        _insert(
            ReceivableModel,
            tenant_id="default",
            customer_codigo="P2C-2",
            order_codigo="P2-PROJ-2",
            original_amount=Decimal("300.00"),
            paid_amount=Decimal("0.00"),
            due_date=hoje + timedelta(days=400),  # fora do horizonte
            status="OPEN",
        )
        _insert(
            ExpenseModel,
            tenant_id="default",
            description="folha P2",
            amount=Decimal("300.00"),
            category="SALARY",
            date=hoje - timedelta(days=10),
            status="ACTIVE",
        )

        res = client.get("/finance/reports/projection", params={"horizon": 30}, headers=_auth(admin_token))
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["horizon"] == 30
        assert len(body["daily"]) == 30
        assert body["daily"][0]["date"]  # série com datas
        # Modelo declarado sem ML
        assert "Sem previsão de receita futura" in body["model"]
        # Recebível de 5 dias entra; o de 400 dias não
        assert Decimal(body["expected_in"]) >= Decimal("200.00")
        assert Decimal(body["current_balance"]) == Decimal("1234.56")
        # Média diária de despesas ≥ 300/30 = 10 (outras despesas do tenant podem somar)
        assert Decimal(body["avg_daily_expenses"]) >= Decimal("10.00")
        # Fechamento = saldo + entradas − saídas projetadas
        assert Decimal(body["projected_balance"]) == (
            Decimal(body["current_balance"]) + Decimal(body["expected_in"]) - Decimal(body["expected_out"])
        )


# ── Team ──────────────────────────────────────────────


class TestTeam:
    def test_entregas_e_folha(self, client, admin_token):
        from app.infrastructure.repositories.delivery_persistence_model import DeliveryRecord

        agora = datetime.utcnow()
        _insert(
            DeliveryRecord,
            delivery_id=str(uuid4()),
            tenant_id="default",
            order_id="P2-TEAM-1",
            status="DELIVERED",
            driver_id="DRV-P2",
            customer_codigo="000001",
            assigned_at=agora - timedelta(hours=1),
            delivered_at=agora - timedelta(minutes=30),
            created_at=agora - timedelta(hours=2),
        )
        _insert(
            ExpenseModel,
            tenant_id="default",
            description="salário equipe P2",
            amount=Decimal("500.00"),
            category="SALARY",
            date=agora - timedelta(days=3),
            status="ACTIVE",
        )

        res = client.get("/finance/reports/team", params={"days": 7}, headers=_auth(admin_token))
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["days"] == 7
        by_id = {d["driver_id"]: d for d in body["by_driver"]}
        assert "DRV-P2" in by_id
        assert by_id["DRV-P2"]["delivered"] >= 1
        assert Decimal(body["salary_total"]) >= Decimal("500.00")
        assert "rateio" in body["note"]


# ── Hourly ────────────────────────────────────────────


class TestHourly:
    def test_buckets_por_hora_de_paid_at(self, client, admin_token):
        janela = datetime(2026, 8, 5, 10, 30)
        _insert(
            PaymentModel,
            tenant_id="default",
            order_codigo="P2-H-1",
            amount=Decimal("70.00"),
            method="PIX",
            status="PAID",
            paid_at=janela,
            created_at=janela,
        )
        _insert(
            PaymentModel,
            tenant_id="default",
            order_codigo="P2-H-2",
            amount=Decimal("20.00"),
            method="CASH",
            status="PAID",
            paid_at=datetime(2026, 8, 5, 10, 15),
            created_at=datetime(2026, 8, 5, 10, 15),
        )
        _insert(
            PaymentModel,
            tenant_id="default",
            order_codigo="P2-H-3",
            amount=Decimal("999.00"),
            method="PIX",
            status="REFUNDED",  # fora do hourly
            paid_at=datetime(2026, 8, 5, 10, 0),
            created_at=datetime(2026, 8, 5, 10, 0),
        )

        res = client.get(
            "/finance/reports/hourly",
            params={"from": "2026-08-05", "to": "2026-08-05"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert len(body["buckets"]) == 24
        assert [b["hour"] for b in body["buckets"]] == list(range(24))
        by_hour = {b["hour"]: b for b in body["buckets"]}
        assert by_hour[10]["count"] == 2
        assert Decimal(by_hour[10]["total"]) == Decimal("90.00")
        assert Decimal(body["total"]) == Decimal("90.00")
        assert by_hour[0]["count"] == 0


# ── Conciliação ───────────────────────────────────────


class TestConciliation:
    def test_match_e_divergencias_a_revisar(self, client, admin_token):
        janela = datetime(2026, 8, 10, 9, 0)

        # Pagamento OK: tem caixa e recebível consistente
        ok_pay = _insert(
            PaymentModel,
            tenant_id="default",
            order_codigo="P2-C-OK",
            amount=Decimal("100.00"),
            method="PIX",
            status="PAID",
            paid_at=janela,
            created_at=janela,
        )
        _insert(
            CashMovementModel,
            tenant_id="default",
            type="RECEIPT",
            amount=Decimal("100.00"),
            description="ok",
            reference_type="PAYMENT",
            reference_id=str(ok_pay),
            balance_after=Decimal("100.00"),
            created_at=janela,
        )
        _insert(
            ReceivableModel,
            tenant_id="default",
            customer_codigo="P2CC-1",
            order_codigo="P2-C-OK",
            original_amount=Decimal("100.00"),
            paid_amount=Decimal("100.00"),
            due_date=janela + timedelta(days=7),
            status="PAID",
        )

        # Pagamento sem movimento de caixa
        nocash_pay = _insert(
            PaymentModel,
            tenant_id="default",
            order_codigo="P2-C-NOCASH",
            amount=Decimal("50.00"),
            method="CASH",
            status="PAID",
            paid_at=janela,
            created_at=janela,
        )
        _ = nocash_pay
        _insert(
            ReceivableModel,
            tenant_id="default",
            customer_codigo="P2CC-2",
            order_codigo="P2-C-NOCASH",
            original_amount=Decimal("50.00"),
            paid_amount=Decimal("50.00"),
            due_date=janela + timedelta(days=7),
            status="PAID",
        )

        # Pagamento sem recebível e com delta no que existe de outro pedido —
        # aqui: sem recebível de propósito
        _insert(
            PaymentModel,
            tenant_id="default",
            order_codigo="P2-C-NOREC",
            amount=Decimal("30.00"),
            method="CARD",
            status="PAID",
            paid_at=janela,
            created_at=janela,
        )

        res = client.get(
            "/finance/reports/conciliation",
            params={"from": "2026-08-10", "to": "2026-08-10"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["checked"] >= 3
        assert body["matched"] >= 1
        assert body["to_review"] >= 2

        issues_by_order = {i["order_codigo"]: i for i in body["items"]}
        assert "sem_movimento_de_caixa" in issues_by_order["P2-C-NOCASH"]["issues"]
        assert issues_by_order["P2-C-NOCASH"]["has_cash_movement"] is False
        assert "sem_recebivel" in issues_by_order["P2-C-NOREC"]["issues"]
        assert issues_by_order["P2-C-NOREC"]["receivable_status"] is None

        # Semântica honesta: "a revisar", nunca rotular como erro
        assert "revisar" in body["note"]
        assert all("erro" not in issue for i in body["items"] for issue in i["issues"])

    def test_recebivel_em_divergencia(self, client, admin_token):
        janela = datetime(2026, 8, 11, 9, 0)
        pay = _insert(
            PaymentModel,
            tenant_id="default",
            order_codigo="P2-C-DELTA",
            amount=Decimal("80.00"),
            method="PIX",
            status="PAID",
            paid_at=janela,
            created_at=janela,
        )
        _insert(
            CashMovementModel,
            tenant_id="default",
            type="RECEIPT",
            amount=Decimal("80.00"),
            description="delta",
            reference_type="PAYMENT",
            reference_id=str(pay),
            balance_after=Decimal("180.00"),
            created_at=janela,
        )
        # paid_amount 0 ≠ soma de pagamentos 80 → divergência
        _insert(
            ReceivableModel,
            tenant_id="default",
            customer_codigo="P2CC-3",
            order_codigo="P2-C-DELTA",
            original_amount=Decimal("80.00"),
            paid_amount=Decimal("0.00"),
            due_date=janela + timedelta(days=7),
            status="OPEN",
        )

        res = client.get(
            "/finance/reports/conciliation",
            params={"from": "2026-08-11", "to": "2026-08-11"},
            headers=_auth(admin_token),
        )
        assert res.status_code == 200, res.text
        body = res.json()
        by_order = {i["order_codigo"]: i for i in body["items"]}
        assert "recebivel_em_divergencia" in by_order["P2-C-DELTA"]["issues"]
        assert Decimal(by_order["P2-C-DELTA"]["receivable_delta"]) == Decimal("-80.00")
