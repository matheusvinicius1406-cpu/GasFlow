"""V7 — guard `finance.read` nos GETs de `/finance/*` e `/reports/*`.

Decisão V7 (docs/auditoria/central-financeira-fase2.md:28): o backend passa a
exigir a permissão nos GETs; DRIVER/CUSTOMER (sessão de painel) ficam de fora.
Escritas continuam só com `get_tenant_context` nesta missão (V3 é gate de front).
"""

import uuid

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


def _token_for_role(client, admin_token, role: str) -> str:
    """Cria usuário com `role`, troca a senha obrigatória e devolve o token."""
    username = f"v7_{role.lower()}_{uuid.uuid4().hex[:6]}"
    res = client.post(
        "/admin/users",
        headers=_auth(admin_token),
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

    changed = client.post(
        "/auth/change-password",
        headers=_auth(token),
        json={"current_password": "InitialPass1!", "new_password": "V7Pass123!"},
    )
    assert changed.status_code == 200, changed.text
    return token


READ_PATHS = (
    "/finance/payments",
    "/finance/cash",
    "/finance/budget",
    "/finance/saved-reports",
    "/finance/receivables/summary",
    "/reports/deliveries",
    "/reports/summary",
)


def test_quem_tem_finance_read_200(client, admin_token):
    token = _token_for_role(client, admin_token, "VIEWER")
    for path in READ_PATHS:
        res = client.get(path, headers=_auth(token))
        assert res.status_code == 200, f"{path} -> {res.status_code}: {res.text[:200]}"


def test_driver_403_nos_gets(client, admin_token):
    token = _token_for_role(client, admin_token, "DRIVER")
    for path in READ_PATHS:
        res = client.get(path, headers=_auth(token))
        assert res.status_code == 403, f"{path} -> {res.status_code}"
        assert "finance.read" in res.json()["detail"]


def test_customer_403_nos_gets(client, admin_token):
    token = _token_for_role(client, admin_token, "CUSTOMER")
    for path in READ_PATHS:
        res = client.get(path, headers=_auth(token))
        assert res.status_code == 403, f"{path} -> {res.status_code}"
        assert "finance.read" in res.json()["detail"]


def test_escritas_continuam_so_com_auth(client, admin_token):
    """V3 ficou de front nesta missão: escritas não ganham gate de permissão.

    VIEWER (sem `finance.write`) ainda consegue editar orçamento — quando o
    gate de escrita chegar ao backend, este teste é o sinal para removê-lo.
    """
    token = _token_for_role(client, admin_token, "VIEWER")
    try:
        res = client.put(
            "/finance/budget",
            headers=_auth(token),
            json={"year": 2035, "month": 6, "items": [{"category": "Teste V7", "amount": "10.00"}]},
        )
        assert res.status_code == 200, res.text
    finally:
        from sqlalchemy.orm import Session

        from app.infrastructure.database.init_db import engine
        from app.infrastructure.repositories.financial_models import FinanceBudgetModel

        db = Session(bind=engine)
        try:
            rows = db.query(FinanceBudgetModel).filter(FinanceBudgetModel.year == 2035, FinanceBudgetModel.month == 6)
            rows.delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()
