"""F10.8 — Relatório por período (GET /finance/reports/period).

A página de Relatórios só mostrava o dia de hoje. Este endpoint entrega o
período escolhido (totais + série diária + comparação com o período anterior
de mesma duração), que é o que a tela passou a consumir.

Cobre: exigência de autenticação, validação de `from`/`to`, período com dias
zerados, comparação e o recorte por tenant.
"""

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.database.init_db import engine
from app.infrastructure.repositories.financial_models import CashMovementModel, ExpenseModel
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


def _seed(dia: datetime, receita: str | None = None, despesa: str | None = None, tenant: str = "default") -> None:
    """Insere movimento/despesa no dia exato (sem depender de 'hoje')."""
    from sqlalchemy.orm import Session

    db = Session(bind=engine)
    try:
        if receita is not None:
            db.add(
                CashMovementModel(
                    tenant_id=tenant,
                    type="RECEIPT",
                    amount=Decimal(receita),
                    description="recebimento de teste",
                    balance_after=Decimal(receita),
                    created_at=dia,
                )
            )
        if despesa is not None:
            db.add(
                ExpenseModel(
                    tenant_id=tenant,
                    description="despesa de teste",
                    amount=Decimal(despesa),
                    category="OTHER",
                    date=dia,
                    status="ACTIVE",
                )
            )
        db.commit()
    finally:
        db.close()


def test_exige_autenticacao(client):
    assert client.get("/finance/reports/period").status_code in (401, 403)


def test_from_sem_to_e_rejeitado(client, admin_token):
    res = client.get("/finance/reports/period", params={"from": "2026-05-01"}, headers=_auth(admin_token))
    assert res.status_code == 400
    assert "from" in res.json()["detail"] and "to" in res.json()["detail"]


def test_data_invalida_e_rejeitada(client, admin_token):
    res = client.get(
        "/finance/reports/period",
        params={"from": "01/05/2026", "to": "2026-05-10"},
        headers=_auth(admin_token),
    )
    assert res.status_code == 400


def test_to_antes_de_from_e_rejeitado(client, admin_token):
    res = client.get(
        "/finance/reports/period",
        params={"from": "2026-05-10", "to": "2026-05-01"},
        headers=_auth(admin_token),
    )
    assert res.status_code == 400


def test_periodo_com_totais_serie_diaria_e_comparacao(client, admin_token):
    janela = datetime(2026, 5, 1)
    # Período anterior: 1-3/mai com 100 de receita
    _seed(datetime(2026, 5, 1, 12, 0), receita="100.00")
    # Período atual: 4-6/mai com 150 de receita e 50 de despesa
    _seed(datetime(2026, 5, 4, 12, 0), receita="50.00", despesa="20.00")
    _seed(datetime(2026, 5, 6, 12, 0), receita="100.00", despesa="30.00")

    res = client.get(
        "/finance/reports/period",
        params={"from": "2026-05-04", "to": "2026-05-06"},
        headers=_auth(admin_token),
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["from"] == "2026-05-04"
    assert body["to"] == "2026-05-06"
    assert body["days"] == 3
    assert Decimal(body["total_receipts"]) == Decimal("150.00")
    assert Decimal(body["total_expenses"]) == Decimal("50.00")
    assert Decimal(body["net_result"]) == Decimal("100.00")

    assert [d["date"] for d in body["daily"]] == ["2026-05-04", "2026-05-05", "2026-05-06"]
    assert Decimal(body["daily"][1]["receipts"]) == Decimal("0.00")

    assert body["previous"]["from"] == "2026-05-01"
    assert Decimal(body["previous"]["total_receipts"]) == Decimal("100.00")
    assert body["comparison"]["receipts_pct"] == 50.0
    assert body["comparison"]["expenses_pct"] is None  # anterior sem despesa


def test_ultimos_dias_incluem_hoje_e_nao_vaza_tenant(client, admin_token):
    """`days=30` cobre de 29 dias atrás até hoje; outro tenant não aparece."""
    from datetime import timedelta

    hoje = datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    _seed(hoje, receita="7.00")
    _seed(hoje, receita="999.00", tenant="outro-tenant")

    res = client.get("/finance/reports/period", params={"days": 30}, headers=_auth(admin_token))
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["days"] == 30
    assert body["to"] == hoje.date().isoformat()
    assert body["from"] == (hoje - timedelta(days=29)).date().isoformat()
    assert len(body["daily"]) == 30

    receitas = sum(Decimal(d["receipts"]) for d in body["daily"])
    assert receitas >= Decimal("7.00")
    assert receitas < Decimal("999.00"), "receita de outro tenant vazou no relatório"
