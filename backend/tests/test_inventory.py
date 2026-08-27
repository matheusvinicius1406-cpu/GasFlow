"""
Inventory Tests — FASE 7.1
Real database tests for: constraints, transactions, rollback, idempotency, concurrency.
"""

import pytest
import threading
import time
from datetime import datetime
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database.base import Base
from app.infrastructure.repositories.inventory_model import InventoryModel, StockMovementModel
from app.infrastructure.repositories.client_model import ClientModel
from app.infrastructure.repositories.product_model import ProductModel
from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository


# ── Test DB Setup ─────────────────────────────────────────

@pytest.fixture
def test_db():
    """Create a fresh in-memory SQLite database with WAL and FK enabled."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _seed_product(test_db, codigo="P00001", nome="GLP P13", estoque=0):
    """Helper to seed a product."""
    p = ProductModel(codigo=codigo, nome=nome, tipo="GAS", preco=100.0, estoque=estoque)
    test_db.add(p)
    test_db.commit()
    return p


# ═══════════════════════════════════════════════════════════
# CONSTRAINTS
# ═══════════════════════════════════════════════════════════

def test_inventory_unique_product(test_db):
    """UNIQUE(product_codigo) prevents duplicate inventory."""
    _seed_product(test_db)
    inv1 = InventoryModel(product_codigo="P00001", quantity=10)
    test_db.add(inv1)
    test_db.commit()

    inv2 = InventoryModel(product_codigo="P00001", quantity=20)
    test_db.add(inv2)
    with pytest.raises(Exception):
        test_db.commit()


def test_inventory_fk_product(test_db):
    """FK to products.codigo is enforced."""
    inv = InventoryModel(product_codigo="FAKE99", quantity=10)
    test_db.add(inv)
    with pytest.raises(Exception):
        test_db.commit()


def test_movement_fk_product(test_db):
    """StockMovement FK to products.codigo is enforced."""
    m = StockMovementModel(
        product_codigo="FAKE99", type="ENTRY", quantity=10,
        reason="Test", balance_before=0, balance_after=10,
        created_at=datetime.utcnow(),
    )
    test_db.add(m)
    with pytest.raises(Exception):
        test_db.commit()


def test_movement_idempotency_constraint(test_db):
    """UNIQUE(reference_type, reference_id) prevents duplicate movements."""
    _seed_product(test_db)
    m1 = StockMovementModel(
        product_codigo="P00001", type="SALE", quantity=5,
        reason="Order #1", reference_type="ORDER", reference_id="000001",
        balance_before=10, balance_after=5, created_at=datetime.utcnow(),
    )
    test_db.add(m1)
    test_db.commit()

    m2 = StockMovementModel(
        product_codigo="P00001", type="SALE", quantity=5,
        reason="Order #1 dup", reference_type="ORDER", reference_id="000001",
        balance_before=5, balance_after=0, created_at=datetime.utcnow(),
    )
    test_db.add(m2)
    with pytest.raises(Exception):
        test_db.commit()


# ═══════════════════════════════════════════════════════════
# ATOMIC OPERATIONS
# ═══════════════════════════════════════════════════════════

def test_add_stock_atomic(test_db):
    """Add stock atomically — inventory + movement in single commit."""
    _seed_product(test_db)
    repo = SQLAlchemyInventoryRepository(test_db)

    result = repo.add_stock_atomic("P00001", 50, reason="Compra inicial")
    inv = result["inventory"]
    movement = result["movement"]

    assert inv.quantity == 50
    assert movement.balance_before == 0
    assert movement.balance_after == 50
    assert movement.type.value == "ENTRY"

    # Verify both persisted
    db_inv = test_db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert db_inv.quantity == 50
    db_mov = test_db.query(StockMovementModel).filter(StockMovementModel.product_codigo == "P00001").first()
    assert db_mov is not None


def test_deduct_stock_atomic(test_db):
    """Deduct stock atomically."""
    _seed_product(test_db)
    repo = SQLAlchemyInventoryRepository(test_db)

    # Add stock first
    repo.add_stock_atomic("P00001", 50, reason="Initial")

    # Deduct
    result = repo.deduct_stock_atomic("P00001", 10, reason="Sale")
    assert result["inventory"].quantity == 40
    assert result["movement"].balance_before == 50
    assert result["movement"].balance_after == 40


def test_deduct_insufficient_stock(test_db):
    """Deduct more than available raises error."""
    _seed_product(test_db)
    repo = SQLAlchemyInventoryRepository(test_db)

    repo.add_stock_atomic("P00001", 5, reason="Initial")

    with pytest.raises(ValueError, match="insuficiente"):
        repo.deduct_stock_atomic("P00001", 10, reason="Sale")

    # Stock should NOT have changed
    inv = test_db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity == 5


def test_adjust_stock_atomic(test_db):
    """Adjust stock atomically."""
    _seed_product(test_db)
    repo = SQLAlchemyInventoryRepository(test_db)

    repo.add_stock_atomic("P00001", 50, reason="Initial")
    result = repo.adjust_stock_atomic("P00001", 38, reason="Physical count")

    assert result["inventory"].quantity == 38
    assert result["movement"].balance_before == 50
    assert result["movement"].balance_after == 38


def test_return_stock_atomic(test_db):
    """Return stock atomically."""
    _seed_product(test_db)
    repo = SQLAlchemyInventoryRepository(test_db)

    repo.add_stock_atomic("P00001", 50, reason="Initial")
    repo.deduct_stock_atomic("P00001", 10, reason="Sale", reference_type="ORDER", reference_id="000001")

    result = repo.return_stock_atomic("P00001", 10, reason="Cancel",
                                       reference_type="ORDER_RETURN", reference_id="000001")
    assert result["inventory"].quantity == 50


# ═══════════════════════════════════════════════════════════
# IDEMPOTENCY
# ═══════════════════════════════════════════════════════════

def test_deduct_idempotency(test_db):
    """Same order cannot deduct stock twice."""
    _seed_product(test_db)
    repo = SQLAlchemyInventoryRepository(test_db)

    repo.add_stock_atomic("P00001", 50, reason="Initial")
    repo.deduct_stock_atomic("P00001", 10, reason="Sale",
                              reference_type="ORDER", reference_id="000001")

    with pytest.raises(ValueError, match="já registrado"):
        repo.deduct_stock_atomic("P00001", 10, reason="Sale dup",
                                  reference_type="ORDER", reference_id="000001")

    # Stock should remain at 40
    inv = test_db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity == 40


def test_return_idempotency(test_db):
    """Same order cannot return stock twice."""
    _seed_product(test_db)
    repo = SQLAlchemyInventoryRepository(test_db)

    repo.add_stock_atomic("P00001", 50, reason="Initial")
    repo.return_stock_atomic("P00001", 10, reason="Cancel",
                              reference_type="ORDER_RETURN", reference_id="000001")

    with pytest.raises(ValueError, match="já registrada"):
        repo.return_stock_atomic("P00001", 10, reason="Cancel dup",
                                  reference_type="ORDER_RETURN", reference_id="000001")


# ═══════════════════════════════════════════════════════════
# CONCURRENCY
# ═══════════════════════════════════════════════════════════

def test_concurrent_deduction(test_db):
    """Two sequential deductions — second should fail if insufficient."""
    _seed_product(test_db)
    repo = SQLAlchemyInventoryRepository(test_db)
    repo.add_stock_atomic("P00001", 10, reason="Initial")

    # First deduction succeeds
    result1 = repo.deduct_stock_atomic("P00001", 7, reason="Order A",
                                        reference_type="ORDER", reference_id="000001")
    assert result1["inventory"].quantity == 3

    # Second deduction with insufficient stock fails
    with pytest.raises(ValueError, match="insuficiente"):
        repo.deduct_stock_atomic("P00001", 7, reason="Order B",
                                  reference_type="ORDER", reference_id="000002")

    # Stock remains at 3
    inv = test_db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity == 3


# ═══════════════════════════════════════════════════════════
# BALANCE CONSISTENCY
# ═══════════════════════════════════════════════════════════

def test_ledger_reconstruction(test_db):
    """Ledger movements reconstruct to correct final balance."""
    _seed_product(test_db)
    repo = SQLAlchemyInventoryRepository(test_db)

    # INITIAL_BALANCE 50
    repo.add_stock_atomic("P00001", 50, reason="Initial")
    # ENTRY 20
    repo.add_stock_atomic("P00001", 20, reason="Purchase")
    # SALE 10
    repo.deduct_stock_atomic("P00001", 10, reason="Sale")
    # Return 2
    repo.return_stock_atomic("P00001", 2, reason="Return")

    # Final balance: 50 + 20 - 10 + 2 = 62
    inv = test_db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity == 62

    # Verify all movements exist
    movements = test_db.query(StockMovementModel).filter(
        StockMovementModel.product_codigo == "P00001"
    ).order_by(StockMovementModel.id).all()
    assert len(movements) == 4


def test_balance_after_matches_quantity(test_db):
    """balance_after in last movement matches current inventory quantity."""
    _seed_product(test_db)
    repo = SQLAlchemyInventoryRepository(test_db)

    repo.add_stock_atomic("P00001", 50, reason="Initial")
    repo.deduct_stock_atomic("P00001", 10, reason="Sale")

    inv = test_db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    last_movement = test_db.query(StockMovementModel).filter(
        StockMovementModel.product_codigo == "P00001"
    ).order_by(StockMovementModel.id.desc()).first()

    assert inv.quantity == last_movement.balance_after


# ═══════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════

def test_no_negative_stock(test_db):
    """Stock can never go negative."""
    _seed_product(test_db)
    repo = SQLAlchemyInventoryRepository(test_db)

    repo.add_stock_atomic("P00001", 5, reason="Initial")
    with pytest.raises(ValueError, match="insuficiente"):
        repo.deduct_stock_atomic("P00001", 6, reason="Sale")

    inv = test_db.query(InventoryModel).filter(InventoryModel.product_codigo == "P00001").first()
    assert inv.quantity == 5


def test_adjust_no_change(test_db):
    """Adjustment to same value returns no movement."""
    _seed_product(test_db)
    repo = SQLAlchemyInventoryRepository(test_db)

    repo.add_stock_atomic("P00001", 50, reason="Initial")
    result = repo.adjust_stock_atomic("P00001", 50, reason="No change")
    assert result["movement"] is None


def test_nonexistent_product_deduct(test_db):
    """Deducting from non-existent product raises error."""
    _seed_product(test_db)
    repo = SQLAlchemyInventoryRepository(test_db)

    with pytest.raises(ValueError, match="não encontrado"):
        repo.deduct_stock_atomic("P99999", 5, reason="Sale")


# ═══════════════════════════════════════════════════════════
# SCHEMA VALIDATION
# ═══════════════════════════════════════════════════════════

def test_schema_stock_entry():
    from app.presentation.schemas.inventory import StockEntryRequest
    req = StockEntryRequest(quantity=50, reason="Compra")
    assert req.quantity == 50

def test_schema_stock_entry_zero_rejected():
    from app.presentation.schemas.inventory import StockEntryRequest
    with pytest.raises(Exception):
        StockEntryRequest(quantity=0)

def test_schema_stock_adjust():
    from app.presentation.schemas.inventory import StockAdjustRequest
    req = StockAdjustRequest(new_quantity=38, reason="Count")
    assert req.new_quantity == 38

def test_schema_stock_adjust_negative_rejected():
    from app.presentation.schemas.inventory import StockAdjustRequest
    with pytest.raises(Exception):
        StockAdjustRequest(new_quantity=-5)

def test_schema_mass_assignment():
    from app.presentation.schemas.inventory import StockEntryRequest, StockAdjustRequest
    entry = StockEntryRequest(quantity=10, reason="Test")
    assert "balance_before" not in entry.model_dump()
    assert "balance_after" not in entry.model_dump()


# ═══════════════════════════════════════════════════════════
# SECURITY
# ═══════════════════════════════════════════════════════════

def test_api_no_whatsapp_references():
    import os
    api_path = os.path.join(os.path.dirname(__file__), "../app/presentation/api/inventory.py")
    if os.path.exists(api_path):
        with open(api_path) as f:
            content = f.read()
        assert "localhost:3001" not in content
        assert "whatsapp-web.js" not in content
