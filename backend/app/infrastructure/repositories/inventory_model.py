"""
Inventory SQLAlchemy Models — FASE 7.1

CRITICAL: UNIQUE(reference_type, reference_id, product_codigo, type) prevents duplicate movements.
Supports multi-item orders and order lifecycle (SALE + RETURN).
Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class InventoryModel(Base):
    """Inventory — single source of truth for stock quantity.

    P0 (Decisão A — aditivo): `quantity` segue sendo o TOTAL operável
    (cheios disponíveis para venda no fluxo atual); quantity_full/
    quantity_empty detalham a física do GLP. Backfill da migração:
    quantity_full = quantity, quantity_empty = 0.
    """

    __tablename__ = "inventory"

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_codigo: Mapped[str] = mapped_column(String, nullable=False, index=True)

    __table_args__ = (UniqueConstraint("tenant_id", "product_codigo", name="uq_inventory_tenant_product"),)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quantity_full: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # P0: cilindros cheios
    quantity_empty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # P0: cilindros vazios (devolução)
    minimum_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    maximum_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class StockMovementModel(Base):
    """StockMovement — immutable ledger of all stock changes."""

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_codigo: Mapped[str] = mapped_column(String, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)  # ENTRY, SALE, ADJUSTMENT, LOSS, RETURN, INITIAL_BALANCE
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)  # Always positive
    # P0 (Decisão B2): detalhe cheio/vazio do movimento — a entrega DELIVERED
    # faz a troca física (1 cheio sai, 1 vazio entra) via DELIVERY_EXCHANGE.
    quantity_full_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quantity_empty_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    reference_type: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # "ORDER", "ORDER_RETURN", "ADJUSTMENT"
    reference_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # order.codigo, etc.

    balance_before: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Placeholder — auth not implemented

    __table_args__ = (
        Index("ix_stock_movements_product", "product_codigo"),
        Index("ix_stock_movements_created", "created_at"),
        Index("ix_stock_movements_reference", "reference_type", "reference_id"),
        # IDEMPOTENCY: Prevent duplicate movements per (reference, product, type).
        # Multi-item orders share reference_id but differ in product_codigo.
        # Order can have SALE + RETURN for same product — differ in type.
        UniqueConstraint(
            "reference_type",
            "reference_id",
            "product_codigo",
            "type",
            name="uq_stock_movements_reference_product_type",
        ),
    )
