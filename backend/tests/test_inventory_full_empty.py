"""Testes P0 3.7 — Estoque cheios/vazios + snapshot diário.

Atualizado para a Decisão B3(a) (14/09/2026): o débito da venda acontece
na entrega DELIVERED (deliver_stock_atomic — debita quantity/quantity_full
e credita quantity_empty); o pedido não debita mais no CONFIRMED.
- Order CONFIRMED: nenhuma movimentação (débito é na entrega)
- DELIVERED: debita cheios + credita vazios, idempotente
- CANCELLED antes de DELIVERED: no-op
- CANCELLED depois de DELIVERED: reversão (RETURN DELIVERY)
- Snapshot diário: idempotente, initial == closing do dia anterior

Invariante mantida em todos os testes:
    quantity == quantity_full

Nota sobre a invariante: `quantity` = cheios operáveis (semântica FASE 7.1
preservada, sem risco de oversell); quantity_empty é rastreado em paralelo
(física da troca). A invariante quantity == full + empty só valeria se a
troca também creditasse quantity — o que conflitaria com a checagem de
estoque vendável do débito atômico.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.application.inventory.snapshot_service import StockDailySnapshotService
from app.infrastructure.database.base import Base
from app.infrastructure.repositories.delivery_persistence_repository import (
    SQLAlchemyDeliveryPersistenceRepository,
)
from app.infrastructure.repositories.inventory_model import InventoryModel, StockMovementModel
from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository
from app.infrastructure.repositories.order_item_model import OrderItemModel
from app.infrastructure.repositories.product_model import ProductModel
from app.infrastructure.repositories.rbac_model import StockDailySnapshotModel


# ── Test DB Setup ─────────────────────────────────────────


@pytest.fixture
def db():
    """Fresh in-memory SQLite with the models used by 3.7."""
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
    """Produto + inventário com composição cheios/vazios explícita.

    quantity = full (invariante A: quantity conta os cheios operáveis).
    """
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
    """Invariante B2/A: quantity == quantity_full (cheios operáveis) para todo produto.

    quantity_empty é rastreamento paralelo da física da troca — nunca entra
    no total operável (ver nota do módulo).
    """
    for inv in db.query(InventoryModel).all():
        assert inv.quantity == inv.quantity_full, (
            f"invariante violada para {inv.product_codigo}: "
            f"quantity={inv.quantity}, full={inv.quantity_full}, empty={inv.quantity_empty}"
        )
        assert inv.quantity >= 0 and inv.quantity_full >= 0 and inv.quantity_empty >= 0


# ═══════════════════════════════════════════════════════════
# RESERVA (Order CONFIRMED)
# ═══════════════════════════════════════════════════════════


def test_order_confirmed_reserves_full(db):
    """CONFIRMED debita quantity E quantity_full (reserva de cheios)."""
    _seed(db, full=10, empty=0)
    repo = SQLAlchemyInventoryRepository(db)

    repo.deduct_stock_atomic("P00001", 4, reason="Venda", reference_type="ORDER", reference_id="000001")

    inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity == 6
    assert inv.quantity_full == 6
    assert inv.quantity_empty == 0

    movement = (
        db.query(StockMovementModel)
        .filter(StockMovementModel.type == "SALE", StockMovementModel.reference_id == "000001")
        .first()
    )
    assert movement is not None
    assert movement.quantity_full_delta == -4
    assert movement.quantity_empty_delta == 0
    _assert_invariant(db)


# ═══════════════════════════════════════════════════════════
# TROCA FÍSICA (Delivery DELIVERED)
# ═══════════════════════════════════════════════════════════


def test_delivery_finalized_debits_and_credits_empty(db):
    """DELIVERED debita cheios (quantity/full) e credita vazios.

    Fluxo completo via repositório de entregas (mesmo caminho das APIs):
    pedido confirmado (sem débito) → entrega DELIVERED debita.
    """
    _seed(db, full=10, empty=2)
    _seed_order_items(db, "000001", [("P00001", 4)])

    # Entrega: DELIVERED dispara o débito (hook do persistence repo)
    delivery_repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
    delivery_repo.create_delivery("d-1", "000001", customer_name="Cliente")
    delivery_repo.assign_delivery("d-1", "drv-1", None, 1)
    delivery_repo.arrive_delivery("d-1", 2)
    result = delivery_repo.complete_delivery("d-1", 3)

    assert result is not None and result.status == "DELIVERED"
    inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity == 6  # 10 - 4 entregues
    assert inv.quantity_full == 6
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
    assert sale.quantity_full_delta == -4
    _assert_invariant(db)


def test_delivery_debit_idempotent(db):
    """Chamar o débito da entrega 2x não duplica movimento nem debita 2x."""
    _seed(db, full=5, empty=0)
    _seed_order_items(db, "000002", [("P00001", 3)])

    delivery_repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
    delivery_repo.create_delivery("d-2", "000002")
    delivery_repo.arrive_delivery("d-2", 1)
    delivery_repo.complete_delivery("d-2", 2)

    # Re-executa o efeito manualmente (o hook é idempotente por movimento)
    delivery_repo._apply_delivery_stock_effect(delivery_repo.get_delivery("d-2"))

    sales = (
        db.query(StockMovementModel)
        .filter(StockMovementModel.type == "SALE", StockMovementModel.reference_id == "d-2")
        .count()
    )
    assert sales == 1

    inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity_empty == 3  # creditado uma única vez
    assert inv.quantity == 2
    assert inv.quantity_full == 2
    _assert_invariant(db)


# ═══════════════════════════════════════════════════════════
# CANCELAMENTOS
# ═══════════════════════════════════════════════════════════


def test_cancelled_before_delivery_no_stock_change(db):
    """CANCELLED antes de DELIVERED: no-op — estoque inalterado."""
    _seed(db, full=10, empty=0)
    _seed_order_items(db, "000003", [("P00001", 4)])

    delivery_repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
    delivery_repo.create_delivery("d-3", "000003")
    delivery_repo.assign_delivery("d-3", "drv-1", None, 1)
    cancelled = delivery_repo.cancel_delivery("d-3", 2)
    assert cancelled is not None and cancelled.status == "CANCELLED"

    inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity == 10
    assert inv.quantity_full == 10
    assert inv.quantity_empty == 0

    # Entrega cancelada NÃO gerou débito nem reversão
    delivery_movements = (
        db.query(StockMovementModel)
        .filter(StockMovementModel.reference_type == "DELIVERY", StockMovementModel.reference_id == "d-3")
        .count()
    )
    assert delivery_movements == 0
    _assert_invariant(db)


def test_cancelled_after_delivery_reverts_debit(db):
    """CANCELLED após DELIVERED: reversão do débito (cheios voltam, vazios saem)."""
    _seed(db, full=10, empty=0)
    _seed_order_items(db, "000004", [("P00001", 4)])

    delivery_repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
    delivery_repo.create_delivery("d-4", "000004")
    delivery_repo.arrive_delivery("d-4", 1)
    delivery_repo.complete_delivery("d-4", 2)  # DELIVERED: débito aplicado

    inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity_empty == 4
    assert inv.quantity == 6

    # Cancelamento após a entrega: dispara a reversão via _transition
    cancelled = delivery_repo.cancel_delivery("d-4", 3)
    assert cancelled is not None and cancelled.status == "CANCELLED"

    inv = db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity == 10  # cheios devolvidos ao estoque
    assert inv.quantity_empty == 0  # vazios removidos (clamp seguro)
    assert inv.quantity_full == 10

    reversal = (
        db.query(StockMovementModel)
        .filter(
            StockMovementModel.type == "RETURN",
            StockMovementModel.reference_type == "DELIVERY",
            StockMovementModel.reference_id == "d-4",
        )
        .first()
    )
    assert reversal is not None
    assert reversal.quantity_empty_delta == -4
    assert reversal.quantity_full_delta == 4
    _assert_invariant(db)


# ═══════════════════════════════════════════════════════════
# SNAPSHOT DIÁRIO
# ═══════════════════════════════════════════════════════════


def test_daily_snapshot_idempotent(db):
    """Rodar o snapshot 2x no mesmo dia não duplica nem sobrescreve initial."""

    _seed(db, full=7, empty=3)
    service = StockDailySnapshotService(db, "default")

    first = service.run_daily_snapshot()
    assert first["created"] == 1

    # Movimenta estoque (ENTRADA de compra) e roda de novo no mesmo dia:
    # closing atualiza, initial preservado
    repo = SQLAlchemyInventoryRepository(db)
    repo.add_stock_atomic("P00001", 5, reason="Compra")
    second = service.run_daily_snapshot()
    assert second["created"] == 0

    snapshots = db.query(StockDailySnapshotModel).all()
    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap.initial_full == 7 and snap.initial_empty == 3  # preservado
    assert snap.closing_full == 12 and snap.closing_empty == 3  # atualizado
    _assert_invariant(db)


def test_snapshot_initial_matches_previous_closing(db):
    """initial(d+1) == closing(d) — cadeia de dias encadeada."""

    _seed(db, full=10, empty=0)
    service = StockDailySnapshotService(db, "default")

    # Dia 1
    service.run_daily_snapshot()
    today_snap = db.query(StockDailySnapshotModel).first()
    day1 = today_snap.snapshot_date

    # Movimenta (entrega debita 4 cheios) e simula o dia seguinte
    repo = SQLAlchemyInventoryRepository(db)
    repo.deliver_stock_atomic("P00001", 4, reason="Venda", reference_type="DELIVERY", reference_id="d-snap")

    day2 = day1 + timedelta(days=1)
    service._snapshot_day(day2)

    snaps = {s.snapshot_date: s for s in db.query(StockDailySnapshotModel).all()}
    assert snaps[day1].closing_full == 10
    assert snaps[day2].initial_full == 10  # herdou o closing do dia anterior
    assert snaps[day2].closing_full == 6  # estado atual após a venda
    _assert_invariant(db)
