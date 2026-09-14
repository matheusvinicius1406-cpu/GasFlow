"""Testes Item 2 — Notas de Compra internas (sem SEFAZ).

Cobre o fluxo completo:
1. Criar nota DRAFT → estoque NÃO muda
2. Confirmar → estoque ENTRA por item (ENTRY idempotente)
3. Cancelar DRAFT → no-op de estoque
4. Cancelar CONFIRMED → 400
5. Editar DRAFT → ok
6. Editar CONFIRMED → 400
7. Confirmar 2x → idempotente (400, sem dupla entrada)
8. Audit log com before/after na confirmação
9. Sequência de note_number por tenant

Estratégia: API HTTP real (TestClient) com o engine isolado do conftest —
mesmo caminho de produção (permissões, tenant, transações).
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

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


def _create_product_with_inventory(db, codigo: str, quantity: int) -> None:
    """Produto + inventário no engine de teste (mesma sessão do app)."""
    from datetime import datetime

    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.inventory_model import InventoryModel
    from app.infrastructure.repositories.product_model import ProductModel

    db.add(ProductModel(codigo=codigo, nome=f"GLP {codigo}", tipo="GAS", preco=100.0, estoque=0))
    db.add(InventoryModel(product_codigo=codigo, quantity=quantity, quantity_full=quantity, quantity_empty=0))
    db.commit()
    _ = datetime, engine  # imports documentais


def _db():
    from sqlalchemy.orm import Session

    from app.infrastructure.database.init_db import engine

    return Session(bind=engine)


def _inventory(db, product_codigo: str):
    from app.infrastructure.repositories.inventory_model import InventoryModel

    return db.query(InventoryModel).filter(InventoryModel.product_codigo == product_codigo).first()


def _note(db, note_id: str):
    from app.infrastructure.repositories.purchase_note_model import PurchaseNoteModel

    return db.query(PurchaseNoteModel).filter(PurchaseNoteModel.id == note_id).first()


def _create_note(client, admin_headers, items, supplier="Fornecedor Teste LTDA") -> dict:
    res = client.post(
        "/purchase-notes",
        headers=admin_headers,
        json={"supplier_name": supplier, "supplier_cnpj": "12.345.678/0001-90", "items": items},
    )
    assert res.status_code == 200, res.text
    return res.json()


# ═══════════════════════════════════════════════════════════
# 1. DRAFT não muda estoque
# ═══════════════════════════════════════════════════════════


def test_create_draft_does_not_change_stock(client, admin_headers):
    db = _db()
    try:
        _create_product_with_inventory(db, f"P{uuid.uuid4().hex[:5].upper()}", 10)
        product = _any_product(db)
        # cria nota para o produto
        codigo = product.product_codigo
        note = _create_note(client, admin_headers, [{"product_codigo": codigo, "quantity": 5, "unit_price": 80.0}])
        assert note["status"] == "DRAFT"

        inv = _inventory(db, codigo)
        assert inv.quantity == 10  # inalterado
        assert inv.quantity_full == 10

        # nenhum movimento de estoque para a nota
        movements = db.execute(
            text("SELECT COUNT(*) FROM stock_movements WHERE reference_type='purchase_note' AND reference_id=:rid"),
            {"rid": note["id"]},
        ).scalar()
        assert movements == 0
    finally:
        db.close()


def _any_product(db):
    from app.infrastructure.repositories.inventory_model import InventoryModel

    return db.query(InventoryModel).first()


# ═══════════════════════════════════════════════════════════
# 2. Confirmar dá entrada por item
# ═══════════════════════════════════════════════════════════


def test_confirm_adds_stock_per_item(client, admin_headers):
    db = _db()
    try:
        c1 = f"P{uuid.uuid4().hex[:5].upper()}"
        c2 = f"P{uuid.uuid4().hex[:5].upper()}"
        _create_product_with_inventory(db, c1, 10)
        _create_product_with_inventory(db, c2, 5)

        note = _create_note(
            client,
            admin_headers,
            [
                {"product_codigo": c1, "quantity": 4, "unit_price": 90.0},
                {"product_codigo": c2, "quantity": 3, "unit_price": 70.0},
            ],
        )
        res = client.post(f"/purchase-notes/{note['id']}/confirm", headers=admin_headers)
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "CONFIRMED"

        inv1, inv2 = _inventory(db, c1), _inventory(db, c2)
        assert inv1.quantity == 14  # 10 + 4
        assert inv1.quantity_full == 14
        assert inv2.quantity == 8  # 5 + 3

        # Invariante do Item 1: quantity == quantity_full
        assert inv1.quantity == inv1.quantity_full
        assert inv2.quantity == inv2.quantity_full

        # Movimento ENTRY registrado (idempotência futura)
        movements = db.execute(
            text(
                "SELECT COUNT(*) FROM stock_movements "
                "WHERE reference_type='purchase_note' AND reference_id=:rid AND type='ENTRY'"
            ),
            {"rid": note["id"]},
        ).scalar()
        assert movements == 2
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# 3-4. Cancelamentos
# ═══════════════════════════════════════════════════════════


def test_cancel_draft_is_noop_on_stock(client, admin_headers):
    db = _db()
    try:
        codigo = f"P{uuid.uuid4().hex[:5].upper()}"
        _create_product_with_inventory(db, codigo, 7)
        note = _create_note(client, admin_headers, [{"product_codigo": codigo, "quantity": 2, "unit_price": 50.0}])

        res = client.post(f"/purchase-notes/{note['id']}/cancel", headers=admin_headers)
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "CANCELLED"

        inv = _inventory(db, codigo)
        assert inv.quantity == 7  # inalterado
        assert inv.quantity_empty == 0
    finally:
        db.close()


def test_cancel_confirmed_returns_400(client, admin_headers):
    db = _db()
    try:
        codigo = f"P{uuid.uuid4().hex[:5].upper()}"
        _create_product_with_inventory(db, codigo, 5)
        note = _create_note(client, admin_headers, [{"product_codigo": codigo, "quantity": 1, "unit_price": 50.0}])
        assert client.post(f"/purchase-notes/{note['id']}/confirm", headers=admin_headers).status_code == 200

        res = client.post(f"/purchase-notes/{note['id']}/cancel", headers=admin_headers)
        assert res.status_code == 400
        assert "DRAFT" in res.json()["detail"]
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# 5-6. Edição
# ═══════════════════════════════════════════════════════════


def test_update_draft_ok(client, admin_headers):
    db = _db()
    try:
        codigo = f"P{uuid.uuid4().hex[:5].upper()}"
        _create_product_with_inventory(db, codigo, 5)
        note = _create_note(client, admin_headers, [{"product_codigo": codigo, "quantity": 1, "unit_price": 50.0}])

        res = client.patch(
            f"/purchase-notes/{note['id']}",
            headers=admin_headers,
            json={"supplier_name": "Novo Fornecedor", "observations": "compra do dia"},
        )
        assert res.status_code == 200, res.text
        assert res.json()["supplier_name"] == "Novo Fornecedor"
    finally:
        db.close()


def test_update_confirmed_returns_400(client, admin_headers):
    db = _db()
    try:
        codigo = f"P{uuid.uuid4().hex[:5].upper()}"
        _create_product_with_inventory(db, codigo, 5)
        note = _create_note(client, admin_headers, [{"product_codigo": codigo, "quantity": 1, "unit_price": 50.0}])
        assert client.post(f"/purchase-notes/{note['id']}/confirm", headers=admin_headers).status_code == 200

        res = client.patch(
            f"/purchase-notes/{note['id']}",
            headers=admin_headers,
            json={"supplier_name": "Não deveria mudar"},
        )
        assert res.status_code == 400
        # Confirma que não mudou
        assert _note(db, note["id"]).supplier_name == "Fornecedor Teste LTDA"
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# 7. Confirmar 2x → idempotente (400, sem dupla entrada)
# ═══════════════════════════════════════════════════════════


def test_confirm_twice_is_rejected(client, admin_headers):
    db = _db()
    try:
        codigo = f"P{uuid.uuid4().hex[:5].upper()}"
        _create_product_with_inventory(db, codigo, 10)
        note = _create_note(client, admin_headers, [{"product_codigo": codigo, "quantity": 3, "unit_price": 60.0}])

        assert client.post(f"/purchase-notes/{note['id']}/confirm", headers=admin_headers).status_code == 200
        second = client.post(f"/purchase-notes/{note['id']}/confirm", headers=admin_headers)
        assert second.status_code == 400

        inv = _inventory(db, codigo)
        assert inv.quantity == 13  # 10 + 3 (uma única vez)
        entries = db.execute(
            text(
                "SELECT COUNT(*) FROM stock_movements "
                "WHERE reference_type='purchase_note' AND reference_id=:rid AND type='ENTRY'"
            ),
            {"rid": note["id"]},
        ).scalar()
        assert entries == 1
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# 8. Audit log com before/after
# ═══════════════════════════════════════════════════════════


def test_confirm_writes_audit_before_after(client, admin_headers):
    db = _db()
    try:
        codigo = f"P{uuid.uuid4().hex[:5].upper()}"
        _create_product_with_inventory(db, codigo, 5)
        note = _create_note(client, admin_headers, [{"product_codigo": codigo, "quantity": 2, "unit_price": 40.0}])
        assert client.post(f"/purchase-notes/{note['id']}/confirm", headers=admin_headers).status_code == 200

        rows = db.execute(
            text(
                "SELECT action, before_json, after_json, details FROM auth_audit_log "
                "WHERE resource='purchase_note' AND resource_id=:rid ORDER BY timestamp"
            ),
            {"rid": note["id"]},
        ).fetchall()
        actions = [r.action for r in rows]
        assert "purchase_note.created" in actions
        assert "purchase_note.confirmed" in actions

        def _as_dict(raw):
            """SQLite devolve JSON como str em raw SQL; ORM devolve dict."""
            return raw if isinstance(raw, dict) else json.loads(raw)

        confirmed = next(r for r in rows if r.action == "purchase_note.confirmed")
        before = _as_dict(confirmed.before_json)
        after = _as_dict(confirmed.after_json)
        details = _as_dict(confirmed.details)
        assert before.get("status") == "DRAFT"
        assert after.get("status") == "CONFIRMED"
        assert details.get("items")
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# 9. note_number sequencial por tenant
# ═══════════════════════════════════════════════════════════


def test_note_number_sequence(client, admin_headers):
    db = _db()
    try:
        codigo = f"P{uuid.uuid4().hex[:5].upper()}"
        _create_product_with_inventory(db, codigo, 5)
        n1 = _create_note(client, admin_headers, [{"product_codigo": codigo, "quantity": 1, "unit_price": 10.0}])
        n2 = _create_note(
            client,
            admin_headers,
            [{"product_codigo": codigo, "quantity": 1, "unit_price": 10.0}],
            supplier="Outro Fornecedor",
        )
        assert n2["note_number"] == n1["note_number"] + 1

        # mesmo número não se repete no tenant (UNIQUE)
        duplicates = db.execute(
            text(
                "SELECT tenant_id, note_number, COUNT(*) c FROM purchase_notes "
                "GROUP BY tenant_id, note_number HAVING c > 1"
            )
        ).fetchall()
        assert duplicates == []
    finally:
        db.close()
