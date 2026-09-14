"""Testes Item 1 — Débito de estoque na ENTREGA (Decisão B3(a), 14/09/2026).

Regra nova: estoque só cai quando o pedido é entregue de fato.
- Order CONFIRMED → NÃO debita (apenas registra)
- Delivery DELIVERED → debita quantity + quantity_full e credita quantity_empty
- Delivery CANCELLED após DELIVERED → reverte tudo
- Order CANCELLED antes de DELIVERED → no-op
- Idempotência: 2x DELIVERED não duplica movimento (constraint
  uq_stock_movements_reference_product_type)
- Migração v3: reverte débitos prematuros de pedidos CONFIRMED antigos,
  idempotente (rodar 2x não corrompe)

Invariante verificada em todos os testes: quantity == quantity_full.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database.base import Base
from app.infrastructure.repositories.delivery_persistence_repository import (
    SQLAlchemyDeliveryPersistenceRepository,
)
from app.infrastructure.repositories.inventory_model import InventoryModel, StockMovementModel
from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository
from app.infrastructure.repositories.order_item_model import OrderItemModel
from app.infrastructure.repositories.order_model import OrderModel
from app.infrastructure.repositories.product_model import ProductModel


# ── Test DB Setup ─────────────────────────────────────────


@pytest.fixture
def db():
    """Fresh in-memory SQLite with all models."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _seed(db, codigo: str = "P00001", full: int = 0, empty: int = 0) -> None:
    """Produto + inventário. quantity = full (invariante A)."""
    db.add(ProductModel(codigo=codigo, nome="GLP P13", tipo="GAS", preco=100.0, estoque=full))
    db.add(InventoryModel(product_codigo=codigo, quantity=full, quantity_full=full, quantity_empty=empty))
    db.commit()


def _seed_order_items(db, order_codigo: str, items: list[tuple[str, int]]) -> None:
    for product_codigo, qty in items:
        db.add(
            OrderItemModel(
                order_codigo=order_codigo,
                product_codigo=product_codigo,
                product_nome=f"Produto {product_codigo}",
                quantity=qty,
                unit_price=100,
                subtotal=100 * qty,
            )
        )
    db.commit()


def _assert_invariant(db) -> None:
    """Invariante: quantity == quantity_full para todo produto; nada negativo."""
    for inv in db.query(InventoryModel).all():
        assert inv.quantity == inv.quantity_full, (
            f"invariante violada para {inv.product_codigo}: "
            f"quantity={inv.quantity}, full={inv.quantity_full}, empty={inv.quantity_empty}"
        )
        assert inv.quantity >= 0 and inv.quantity_full >= 0 and inv.quantity_empty >= 0


# ═══════════════════════════════════════════════════════════
# 1. CONFIRMED não debita
# ═══════════════════════════════════════════════════════════


def test_order_confirmed_does_not_debit_stock(db):
    """Após CONFIRMED, estoque inalterado (débito é na entrega)."""
    _seed(db, full=10, empty=0)
    _seed_order_items(db, "000001", [("P00001", 4)])

    from app.application.order.use_cases import UpdateOrderStatusUseCase

    uc = UpdateOrderStatusUseCase(repository=None, inventory_repo=None, order_item_repo=None)
    # O use case busca o pedido pelo repositório; usamos o modelo direto
    # para simular a mudança de status sem depender do OrderRepository.
    order = db.query(OrderModel).filter(OrderModel.codigo == "000001").first()
    assert order is None  # sanity: sem pedido criado, use case não faz nada

    # Confirmação via UpdateOrderStatusUseCase com repositório real:
    from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository

    # cria o pedido no banco (status PENDING)
    db.add(
        OrderModel(
            codigo="000001",
            client_codigo="000001",
            address_snapshot="Rua A, 1",
            status="PENDING",
        )
    )
    db.commit()

    uc = UpdateOrderStatusUseCase(
        repository=SQLAlchemyOrderRepository(db),
        inventory_repo=SQLAlchemyInventoryRepository(db),
        order_item_repo=None,
    )
    uc.execute("000001", "CONFIRMED")

    inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity == 10
    assert inv.quantity_full == 10
    assert inv.quantity_empty == 0

    sales = (
        db.query(StockMovementModel)
        .filter(StockMovementModel.reference_id == "000001", StockMovementModel.type == "SALE")
        .count()
    )
    assert sales == 0
    _assert_invariant(db)


# ═══════════════════════════════════════════════════════════
# 2-3. DELIVERED debita cheios e credita vazios
# ═══════════════════════════════════════════════════════════


def test_delivery_delivered_debits_stock(db):
    """Após DELIVERED, quantity e quantity_full caem."""
    _seed(db, full=10, empty=2)
    _seed_order_items(db, "000001", [("P00001", 4)])

    delivery_repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
    delivery_repo.create_delivery("d-1", "000001", customer_name="Cliente")
    delivery_repo.assign_delivery("d-1", "drv-1", None, 1)
    delivery_repo.arrive_delivery("d-1", 2)
    result = delivery_repo.complete_delivery("d-1", 3)
    assert result is not None and result.status == "DELIVERED"

    inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity == 6
    assert inv.quantity_full == 6

    sale = (
        db.query(StockMovementModel)
        .filter(
            StockMovementModel.type == "SALE",
            StockMovementModel.reference_type == "DELIVERY",
            StockMovementModel.reference_id == "d-1",
        )
        .first()
    )
    assert sale is not None
    assert sale.quantity_full_delta == -4
    _assert_invariant(db)


def test_delivery_delivered_credits_empty(db):
    """Após DELIVERED, quantity_empty sobe (troca física do GLP)."""
    _seed(db, full=10, empty=2)
    _seed_order_items(db, "000001", [("P00001", 4)])

    delivery_repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
    delivery_repo.create_delivery("d-1", "000001", customer_name="Cliente")
    delivery_repo.arrive_delivery("d-1", 1)
    delivery_repo.complete_delivery("d-1", 2)

    inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity_empty == 6  # 2 + 4 devolvidos pelo cliente

    sale = (
        db.query(StockMovementModel)
        .filter(
            StockMovementModel.type == "SALE",
            StockMovementModel.reference_type == "DELIVERY",
            StockMovementModel.reference_id == "d-1",
        )
        .first()
    )
    assert sale is not None
    assert sale.quantity_empty_delta == 4
    _assert_invariant(db)


# ═══════════════════════════════════════════════════════════
# 4-5. Cancelamentos
# ═══════════════════════════════════════════════════════════


def test_delivery_cancelled_after_delivered_reverts(db):
    """CANCELLED após DELIVERED: estoque volta ao estado original."""
    _seed(db, full=10, empty=2)
    _seed_order_items(db, "000001", [("P00001", 4)])

    delivery_repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
    delivery_repo.create_delivery("d-1", "000001", customer_name="Cliente")
    delivery_repo.arrive_delivery("d-1", 1)
    delivery_repo.complete_delivery("d-1", 2)  # DELIVERED: debita

    inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert (inv.quantity, inv.quantity_full, inv.quantity_empty) == (6, 6, 6)

    cancelled = delivery_repo.cancel_delivery("d-1", 3)
    assert cancelled is not None and cancelled.status == "CANCELLED"

    inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert (inv.quantity, inv.quantity_full, inv.quantity_empty) == (10, 10, 2)

    reversal = (
        db.query(StockMovementModel)
        .filter(
            StockMovementModel.type == "RETURN",
            StockMovementModel.reference_type == "DELIVERY",
            StockMovementModel.reference_id == "d-1",
        )
        .first()
    )
    assert reversal is not None
    assert reversal.quantity_full_delta == 4
    assert reversal.quantity_empty_delta == -4
    _assert_invariant(db)


def test_order_cancelled_before_delivered_does_not_change_stock(db):
    """Pedido cancelado antes da entrega: no-op total (nada foi debitado)."""
    _seed(db, full=10, empty=0)
    _seed_order_items(db, "000001", [("P00001", 4)])

    from app.application.order.use_cases import UpdateOrderStatusUseCase
    from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository

    db.add(
        OrderModel(
            codigo="000001",
            client_codigo="000001",
            address_snapshot="Rua A, 1",
            status="CONFIRMED",
        )
    )
    db.commit()

    uc = UpdateOrderStatusUseCase(
        repository=SQLAlchemyOrderRepository(db),
        inventory_repo=SQLAlchemyInventoryRepository(db),
        order_item_repo=None,
    )
    uc.execute("000001", "CANCELLED")

    inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert (inv.quantity, inv.quantity_full, inv.quantity_empty) == (10, 10, 0)

    movements = db.query(StockMovementModel).filter(StockMovementModel.reference_id == "000001").count()
    assert movements == 0
    _assert_invariant(db)


# ═══════════════════════════════════════════════════════════
# 6. Idempotência do DELIVERED
# ═══════════════════════════════════════════════════════════


def test_delivery_idempotent(db):
    """2x DELIVERED não duplica movimento nem debita 2x."""
    _seed(db, full=10, empty=0)
    _seed_order_items(db, "000001", [("P00001", 4)])

    delivery_repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
    delivery_repo.create_delivery("d-1", "000001", customer_name="Cliente")
    delivery_repo.arrive_delivery("d-1", 1)
    delivery_repo.complete_delivery("d-1", 2)

    # Re-executa o efeito manualmente (o hook é idempotente por movimento)
    delivery_repo._apply_delivery_stock_effect(delivery_repo.get_delivery("d-1"))

    sales = (
        db.query(StockMovementModel)
        .filter(
            StockMovementModel.type == "SALE",
            StockMovementModel.reference_type == "DELIVERY",
            StockMovementModel.reference_id == "d-1",
        )
        .count()
    )
    assert sales == 1

    inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert (inv.quantity, inv.quantity_full, inv.quantity_empty) == (6, 6, 4)
    _assert_invariant(db)


# ═══════════════════════════════════════════════════════════
# 7-8. Migração v3 (reversão de débitos prematuros)
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def migration_db(monkeypatch):
    """SQLite em arquivo com o estado 'pré-v3': pedido CONFIRMED debitado."""
    import tempfile

    tmp = tempfile.mktemp(suffix=".db")
    engine = create_engine(f"sqlite:///{tmp}")

    @event.listens_for(engine, "connect")
    def set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Pedido CONFIRMED com débito prematuro (fluxo antigo)
    session.add(ProductModel(codigo="P00001", nome="GLP P13", tipo="GAS", preco=100.0, estoque=6))
    session.add(InventoryModel(product_codigo="P00001", quantity=6, quantity_full=6, quantity_empty=0))
    session.add(
        OrderModel(
            codigo="000042",
            client_codigo="000001",
            address_snapshot="Rua A, 1",
            status="CONFIRMED",
        )
    )
    session.add(
        OrderItemModel(
            order_codigo="000042",
            product_codigo="P00001",
            product_nome="GLP P13",
            quantity=4,
            unit_price=100,
            subtotal=400,
        )
    )
    session.add(
        StockMovementModel(
            product_codigo="P00001",
            type="SALE",
            quantity=4,
            quantity_full_delta=-4,
            quantity_empty_delta=0,
            reason="Venda — Pedido #000042",
            reference_type="ORDER",
            reference_id="000042",
            balance_before=10,
            balance_after=6,
            created_at=datetime.utcnow(),
        )
    )
    session.commit()

    # init_db usa um engine global: apontamos para o engine do teste
    from app.infrastructure.database import init_db as init_db_module

    monkeypatch.setattr(init_db_module, "engine", engine)
    yield session, engine, init_db_module
    session.close()
    engine.dispose()
    import os

    if os.path.exists(tmp):
        os.remove(tmp)


def test_migration_reverts_premature_debits(migration_db):
    """Pedido CONFIRMED antigo tem o débito revertido pela migração v3."""
    session, engine, init_db_module = migration_db

    init_db_module._revert_premature_stock_debits()

    inv = session.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity == 10
    assert inv.quantity_full == 10
    assert inv.quantity_empty == 0

    reversal = (
        session.query(StockMovementModel)
        .filter(
            StockMovementModel.type == "RESERVATION_REVERSAL",
            StockMovementModel.reference_id == "revert:000042",
        )
        .first()
    )
    assert reversal is not None
    assert reversal.quantity == 4

    # Audit trail gravado
    audit = session.execute(text("SELECT details FROM auth_audit_log WHERE resource_id = 'revert:000042'")).fetchone()
    assert audit is not None

    # Marca de controle criada
    marker = session.execute(text("SELECT id FROM system_settings WHERE id = 'stock_debit_migration_v3'")).fetchone()
    assert marker is not None


def test_migration_idempotent(migration_db):
    """Rodar a migração 2x não corrompe estoque (marca de controle)."""
    session, engine, init_db_module = migration_db

    init_db_module._revert_premature_stock_debits()
    init_db_module._revert_premature_stock_debits()  # no-op

    inv = session.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity == 10  # não creditou 2x (seria 14)

    reversals = session.query(StockMovementModel).filter(StockMovementModel.type == "RESERVATION_REVERSAL").count()
    assert reversals == 1
