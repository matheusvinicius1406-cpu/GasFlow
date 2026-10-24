"""Readiness — fluxo completo de conclusão de entrega pelo app (frente MOBILE-P0).

Regressão do P0-1 da auditoria: o backend exige `ARRIVED` para concluir, mas o
app não tinha ação de chegada. Agora o app chama
`POST /driver/deliveries/{id}/arrive`; este teste prova o **contrato do fluxo**
pelas rotas que o app realmente usa (`/driver/*`, auth principal):

- `start` (ASSIGNED ou DISPATCHED) → EN_ROUTE
- `arrive` (EN_ROUTE) → ARRIVED — obrigatório
- `complete` fora de ARRIVED → 400 INVALID_STATE (não pula chegada)
- `complete` (ARRIVED) → DELIVERED
- toque duplicado sem `client_action_id` → 400/409, nunca estado corrompido
- `fail` também a partir de ARRIVED (mesma matriz do backend `can_fail`)

Não depende de Android nem de Docker: TestClient + banco efêmero.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _active_driver(client, admin_headers, tag: str):
    res = client.post(
        "/admin/drivers",
        headers=admin_headers,
        json={
            "name": f"Entregador {tag}",
            "phone": "91999990001",
            "document": "222.222.222-22",
            "username": f"flow_{tag}_{uuid.uuid4().hex[:6]}",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()

    login = client.post(
        "/auth/login",
        json={"username": body["username"], "password": body["temporary_password"]},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['token']}"}

    changed = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": body["temporary_password"], "new_password": "NovaSenha123"},
    )
    assert changed.status_code == 200, changed.text
    return body["driver_id"], headers


def _assigned_delivery(client, admin_headers, driver_id: str) -> str:
    created = client.post(
        "/delivery/deliveries",
        headers=admin_headers,
        json={
            "order_id": f"ord_{uuid.uuid4().hex[:10]}",
            "customer_codigo": f"cli_{uuid.uuid4().hex[:6]}",
            "customer_name": "Cliente Fluxo",
            "notes": "teste do fluxo arrive",
        },
    )
    assert created.status_code == 200, created.text
    delivery_id = created.json()["delivery"]["id"]

    assigned = client.patch(
        f"/delivery/deliveries/{delivery_id}/assign",
        headers=admin_headers,
        json={"driver_id": driver_id},
    )
    assert assigned.status_code == 200, assigned.text
    return delivery_id


def _status(client, headers, delivery_id: str) -> str:
    res = client.get("/driver/deliveries", headers=headers)
    assert res.status_code == 200, res.text
    for record in res.json()["deliveries"]:
        if record["id"] == delivery_id:
            return record["status"]
    raise AssertionError(f"entrega {delivery_id} ausente da lista do entregador")


# ── Fluxo feliz ────────────────────────────────────────────────


def test_fluxo_completo_start_arrive_complete(client, admin_headers):
    """ASSIGNED → EN_ROUTE → ARRIVED → DELIVERED pelas rotas do app."""
    driver_id, headers = _active_driver(client, admin_headers, "f1")
    delivery_id = _assigned_delivery(client, admin_headers, driver_id)

    start = client.post(f"/driver/deliveries/{delivery_id}/start", headers=headers, json={})
    assert start.status_code == 200, start.text
    assert _status(client, headers, delivery_id) == "EN_ROUTE"

    arrive = client.post(f"/driver/deliveries/{delivery_id}/arrive", headers=headers, json={})
    assert arrive.status_code == 200, arrive.text
    assert _status(client, headers, delivery_id) == "ARRIVED"

    complete = client.post(
        f"/driver/deliveries/{delivery_id}/complete",
        headers=headers,
        json={"proof_type": "MANUAL_CONFIRMATION"},
    )
    assert complete.status_code == 200, complete.text
    assert _status(client, headers, delivery_id) == "DELIVERED"


def test_arrive_apos_start_e_obrigatorio_para_concluir(client, admin_headers):
    """Concluir direto (sem chegar) é 400 — o app só libera o botão em ARRIVED."""
    driver_id, headers = _active_driver(client, admin_headers, "f2")
    delivery_id = _assigned_delivery(client, admin_headers, driver_id)

    assert client.post(f"/driver/deliveries/{delivery_id}/start", headers=headers, json={}).status_code == 200

    premature = client.post(f"/driver/deliveries/{delivery_id}/complete", headers=headers, json={})
    assert premature.status_code == 400, premature.text
    assert "INVALID_STATE" in premature.text
    assert _status(client, headers, delivery_id) == "EN_ROUTE", "recusa não pode mudar o estado"


# ── Matriz de estados (espelho das regras do domínio) ───────────


def test_matriz_de_capacidade_do_app_espelha_o_backend():
    """A matriz `can_*` do backend é a mesma que `mobile/src/logic/deliveryFlow.ts` espelha.

    Os guards dos handlers (`handle_*_delivery`) são o contrato de runtime —
    a `_transition` do repositório não valida `DELIVERY_TRANSITIONS`, então a
    autoridade real é esta matriz. O app do entregador habilita botões por ela.
    """
    from pathlib import Path

    source = (Path(__file__).parents[1] / "app" / "presentation" / "api" / "logistics" / "driver_api.py").read_text(
        encoding="utf-8"
    )
    for line in (
        '"can_start": status in ("ASSIGNED", "DISPATCHED")',
        '"can_arrive": status == "EN_ROUTE"',
        '"can_complete": status == "ARRIVED"',
        '"can_fail": status in ("EN_ROUTE", "ARRIVED")',
    ):
        assert line in source, f"capability matrix mudou: {line!r} — atualizar mobile deliveryFlow.ts"


def test_arrive_fora_de_en_route_e_recusado(client, admin_headers):
    """Chegada sem rota (ASSIGNED) e chegada repetida não corrompem o estado."""
    driver_id, headers = _active_driver(client, admin_headers, "f4")
    delivery_id = _assigned_delivery(client, admin_headers, driver_id)

    early = client.post(f"/driver/deliveries/{delivery_id}/arrive", headers=headers, json={})
    assert early.status_code == 400, early.text
    assert _status(client, headers, delivery_id) == "ASSIGNED"

    assert client.post(f"/driver/deliveries/{delivery_id}/start", headers=headers, json={}).status_code == 200
    assert client.post(f"/driver/deliveries/{delivery_id}/arrive", headers=headers, json={}).status_code == 200

    # Toque repetido do botão "Cheguei ao destino" (sem client_action_id):
    # recusa, mas DELIVERED/ARRIVED nunca retrocede.
    duplicate = client.post(f"/driver/deliveries/{delivery_id}/arrive", headers=headers, json={})
    assert duplicate.status_code == 400, duplicate.text
    assert _status(client, headers, delivery_id) == "ARRIVED"


def test_fail_permittido_tambem_em_arrived(client, admin_headers):
    """Espelho de can_fail: o entregador pode reportar problema antes ou na chegada."""
    driver_id, headers = _active_driver(client, admin_headers, "f5")
    delivery_id = _assigned_delivery(client, admin_headers, driver_id)

    assert client.post(f"/driver/deliveries/{delivery_id}/start", headers=headers, json={}).status_code == 200
    assert client.post(f"/driver/deliveries/{delivery_id}/arrive", headers=headers, json={}).status_code == 200

    failed = client.post(
        f"/driver/deliveries/{delivery_id}/fail",
        headers=headers,
        json={"failure_reason": "OTHER"},
    )
    assert failed.status_code == 200, failed.text
    assert _status(client, headers, delivery_id) == "FAILED"


# ── Proteções de acesso ────────────────────────────────────────


def test_arrive_exige_token_e_escopo_de_driver(client, admin_headers):
    """A rota nova do app segue a MESMA proteção das demais (/driver/*)."""
    driver_id, driver_headers = _active_driver(client, admin_headers, "f6")
    delivery_id = _assigned_delivery(client, admin_headers, driver_id)

    anonymous = client.post(f"/driver/deliveries/{delivery_id}/arrive", json={})
    assert anonymous.status_code == 401, anonymous.text

    admin = client.post(f"/driver/deliveries/{delivery_id}/arrive", headers=admin_headers, json={})
    assert admin.status_code == 403, admin.text

    other_id, other_headers = _active_driver(client, admin_headers, "f6b")
    other_delivery = _assigned_delivery(client, admin_headers, other_id)
    cross = client.post(f"/driver/deliveries/{other_delivery}/arrive", headers=driver_headers, json={})
    assert cross.status_code == 404, f"entregador não pode marcar chegada em entrega alheia: {cross.text}"
