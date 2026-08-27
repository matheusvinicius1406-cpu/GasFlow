"""
Inventory SQLAlchemy Models — FASE 7.1

CRITICAL: UNIQUE(reference_type, reference_id, product_codigo, type) prevents duplicate movements.
Supports multi-item orders and order lifecycle (SALE + RETURN).
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey,
    Index, UniqueConstraint, Text
)
from datetime import datetime
from app.infrastructure.database.base import Base


class InventoryModel(Base):
    """Inventory — single source of truth for stock quantity."""
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    product_codigo = Column(
        String,
        ForeignKey("products.codigo"),
        unique=True,
        nullable=False,
        index=True,
    )
    quantity = Column(Integer, nullable=False, default=0)
    minimum_quantity = Column(Integer, nullable=False, default=0)
    maximum_quantity = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class StockMovementModel(Base):
    """StockMovement — immutable ledger of all stock changes."""
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)
    product_codigo = Column(
        String,
        ForeignKey("products.codigo"),
        nullable=False,
        index=True,
    )
    type = Column(String, nullable=False)  # ENTRY, SALE, ADJUSTMENT, LOSS, RETURN, INITIAL_BALANCE
    quantity = Column(Integer, nullable=False)  # Always positive
    reason = Column(Text, nullable=False)

    reference_type = Column(String, nullable=True)  # "ORDER", "ORDER_RETURN", "ADJUSTMENT"
    reference_id = Column(String, nullable=True)     # order.codigo, etc.

    balance_before = Column(Integer, nullable=False, default=0)
    balance_after = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String, nullable=True)  # Placeholder — auth not implemented

    __table_args__ = (
        Index("ix_stock_movements_product", "product_codigo"),
        Index("ix_stock_movements_created", "created_at"),
        Index("ix_stock_movements_reference", "reference_type", "reference_id"),
        # IDEMPOTENCY: Prevent duplicate movements per (reference, product, type).
        # Multi-item orders share reference_id but differ in product_codigo.
        # Order can have SALE + RETURN for same product — differ in type.
        UniqueConstraint(
            "reference_type", "reference_id", "product_codigo", "type",
            name="uq_stock_movements_reference_product_type",
        ),
    )
