"""
Inventory Repository Implementation — FASE 7.1

CRITICAL FIX: All stock operations are now atomic.
Single transaction: validate → update quantity → insert movement.
On error: ROLLBACK both.

Idempotency: UNIQUE(reference_type, reference_id, product_codigo, type) prevents duplicate movements.
Concurrency: Atomic UPDATE with WHERE quantity >= N prevents negative stock.
"""

from datetime import datetime
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from app.domain.inventory.entity import Inventory
from app.domain.inventory.stock_movement import StockMovement, MovementType
from app.domain.inventory.repository import InventoryRepository
from app.infrastructure.repositories.inventory_model import InventoryModel, StockMovementModel


class SQLAlchemyInventoryRepository(InventoryRepository):
    """Implementation with atomic stock operations."""

    def __init__(self, db: Session):
        self.db = db

    # ── Entity Conversion ──────────────────────────────────

    def _to_entity(self, model: InventoryModel) -> Inventory:
        return Inventory(
            id=model.id,
            product_codigo=model.product_codigo,
            quantity=model.quantity,
            minimum_quantity=model.minimum_quantity,
            maximum_quantity=model.maximum_quantity,
            updated_at=model.updated_at,
        )

    def _movement_to_entity(self, model: StockMovementModel) -> StockMovement:
        return StockMovement(
            id=model.id,
            product_codigo=model.product_lineno if hasattr(model, 'product_lineno') else model.product_codigo,
            type=MovementType(model.type),
            quantity=model.quantity,
            reason=model.reason,
            reference_type=model.reference_type,
            reference_id=model.reference_id,
            balance_before=model.balance_before,
            balance_after=model.balance_after,
            created_at=model.created_at,
            created_by=model.created_by,
        )

    # ── Read Operations ────────────────────────────────────

    def get_by_product(self, product_codigo: str) -> Optional[Inventory]:
        model = self.db.query(InventoryModel).filter(
            InventoryModel.product_codigo == product_codigo
        ).first()
        return self._to_entity(model) if model else None

    def get_or_create(self, product_codigo: str, initial_quantity: int = 0) -> Inventory:
        model = self.db.query(InventoryModel).filter(
            InventoryModel.product_codigo == product_codigo
        ).first()
        if model:
            return self._to_entity(model)

        model = InventoryModel(
            product_codigo=product_codigo,
            quantity=initial_quantity,
            minimum_quantity=0,
        )
        self.db.add(model)
        self.db.flush()
        return self._to_entity(model)

    def list_all(self, stock_status: Optional[str] = None,
                 product_type: Optional[str] = None) -> List[Inventory]:
        q = self.db.query(InventoryModel)
        models = q.all()
        entities = [self._to_entity(m) for m in models]

        if stock_status is not None:
            entities = [e for e in entities if e.stock_status.value == stock_status]

        return entities

    def get_movements(self, product_codigo: str,
                      page: int = 1, page_size: int = 20) -> Tuple[List[StockMovement], int]:
        q = self.db.query(StockMovementModel).filter(
            StockMovementModel.product_codigo == product_codigo
        )
        total = q.count()
        offset = (page - 1) * page_size
        models = q.order_by(StockMovementModel.created_at.desc()).offset(offset).limit(page_size).all()
        return [self._movement_to_entity(m) for m in models], total

    def get_movement_by_reference(self, reference_type: str,
                                  reference_id: str,
                                  product_codigo: Optional[str] = None,
                                  movement_type: Optional[str] = None) -> Optional[StockMovement]:
        q = self.db.query(StockMovementModel).filter(
            StockMovementModel.reference_type == reference_type,
            StockMovementModel.reference_id == reference_id,
        )
        if product_codigo:
            q = q.filter(StockMovementModel.product_codigo == product_codigo)
        if movement_type:
            q = q.filter(StockMovementModel.type == movement_type)
        model = q.first()
        return self._movement_to_entity(model) if model else None

    def has_movement_by_reference(self, reference_type: str,
                                  reference_id: str) -> bool:
        """Check if ANY movement exists for a given reference (any product/type)."""
        model = self.db.query(StockMovementModel).filter(
            StockMovementModel.reference_type == reference_type,
            StockMovementModel.reference_id == reference_id,
        ).first()
        return model is not None

    # ── Atomic Write Operations ────────────────────────────

    def _create_movement_model(self, movement: StockMovement) -> StockMovementModel:
        return StockMovementModel(
            product_codigo=movement.product_codigo,
            type=movement.type.value,
            quantity=movement.quantity,
            reason=movement.reason,
            reference_type=movement.reference_type,
            reference_id=movement.reference_id,
            balance_before=movement.balance_before,
            balance_after=movement.balance_after,
            created_at=movement.created_at or datetime.utcnow(),
            created_by=movement.created_by,
        )

    def add_stock_atomic(self, product_codigo: str, quantity: int,
                         reason: str, reference_type: Optional[str] = None,
                         reference_id: Optional[str] = None) -> dict:
        """ATOMIC: Add stock + create movement in single transaction."""
        now = datetime.utcnow()

        # Check idempotency (per product + type)
        if reference_type and reference_id:
            existing = self.db.query(StockMovementModel).filter(
                StockMovementModel.reference_type == reference_type,
                StockMovementModel.reference_id == reference_id,
                StockMovementModel.product_codigo == product_codigo,
                StockMovementModel.type == MovementType.ENTRY.value,
            ).first()
            if existing:
                raise ValueError(f"Movimento já registrado para {reference_type} #{reference_id} no produto {product_codigo}")

        # Get or create inventory
        inv_model = self.db.query(InventoryModel).filter(
            InventoryModel.product_codigo == product_codigo
        ).first()
        if not inv_model:
            inv_model = InventoryModel(
                product_codigo=product_codigo, quantity=0, minimum_quantity=0
            )
            self.db.add(inv_model)
            self.db.flush()

        balance_before = inv_model.quantity
        balance_after = balance_before + quantity

        # Update inventory
        inv_model.quantity = balance_after
        inv_model.updated_at = now

        # Create movement
        movement_model = StockMovementModel(
            product_codigo=product_codigo,
            type=MovementType.ENTRY.value,
            quantity=quantity,
            reason=reason,
            reference_type=reference_type,
            reference_id=reference_id,
            balance_before=balance_before,
            balance_after=balance_after,
            created_at=now,
        )
        self.db.add(movement_model)

        # SINGLE COMMIT — atomic
        self.db.commit()
        self.db.refresh(inv_model)
        self.db.refresh(movement_model)

        return {
            "inventory": self._to_entity(inv_model),
            "movement": self._movement_to_entity(movement_model),
        }

    def deduct_stock_atomic(self, product_codigo: str, quantity: int,
                            reason: str, reference_type: Optional[str] = None,
                            reference_id: Optional[str] = None) -> dict:
        """ATOMIC: Deduct stock + create movement in single transaction.

        Uses UPDATE WHERE quantity >= N for concurrency safety.
        Returns INSUFFICIENT_STOCK if not enough stock.
        """
        now = datetime.utcnow()

        # Check idempotency (per product + type)
        if reference_type and reference_id:
            existing = self.db.query(StockMovementModel).filter(
                StockMovementModel.reference_type == reference_type,
                StockMovementModel.reference_id == reference_id,
                StockMovementModel.product_codigo == product_codigo,
                StockMovementModel.type == MovementType.SALE.value,
            ).first()
            if existing:
                raise ValueError(f"Movimento já registrado para {reference_type} #{reference_id} no produto {product_codigo}")

        # Atomic UPDATE: only succeeds if quantity >= requested
        result = self.db.execute(
            text("UPDATE inventory SET quantity = quantity - :qty, "
                 "updated_at = :now "
                 "WHERE product_codigo = :code AND quantity >= :qty"),
            {"qty": quantity, "now": now, "code": product_codigo}
        )

        if result.rowcount == 0:
            # Either product doesn't exist or insufficient stock
            self.db.rollback()
            inv = self.db.query(InventoryModel).filter(
                InventoryModel.product_codigo == product_codigo
            ).first()
            if not inv:
                raise ValueError(f"Inventário não encontrado para produto {product_codigo}")
            raise ValueError(
                f"Estoque insuficiente. Disponível: {inv.quantity}, solicitado: {quantity}"
            )

        # Read the updated inventory
        inv_model = self.db.query(InventoryModel).filter(
            InventoryModel.product_codigo == product_codigo
        ).first()
        balance_before = inv_model.quantity + quantity  # reverse the update
        balance_after = inv_model.quantity

        # Create movement
        movement_model = StockMovementModel(
            product_codigo=product_codigo,
            type=MovementType.SALE.value,
            quantity=quantity,
            reason=reason,
            reference_type=reference_type,
            reference_id=reference_id,
            balance_before=balance_before,
            balance_after=balance_after,
            created_at=now,
        )
        self.db.add(movement_model)

        # SINGLE COMMIT — atomic
        self.db.commit()
        self.db.refresh(movement_model)

        return {
            "inventory": self._to_entity(inv_model),
            "movement": self._movement_to_entity(movement_model),
        }

    def adjust_stock_atomic(self, product_codigo: str, new_quantity: int,
                            reason: str) -> dict:
        """ATOMIC: Adjust stock + create movement in single transaction."""
        now = datetime.utcnow()

        inv_model = self.db.query(InventoryModel).filter(
            InventoryModel.product_codigo == product_codigo
        ).first()
        if not inv_model:
            self.db.rollback()
            raise ValueError(f"Inventário não encontrado para produto {product_codigo}")

        balance_before = inv_model.quantity
        if balance_before == new_quantity:
            return {"inventory": self._to_entity(inv_model), "movement": None}

        # Update inventory
        inv_model.quantity = new_quantity
        inv_model.updated_at = now

        # Create movement
        movement_model = StockMovementModel(
            product_codigo=product_codigo,
            type=MovementType.ADJUSTMENT.value,
            quantity=abs(new_quantity - balance_before),
            reason=reason,
            reference_type="ADJUSTMENT",
            balance_before=balance_before,
            balance_after=new_quantity,
            created_at=now,
        )
        self.db.add(movement_model)

        # SINGLE COMMIT
        self.db.commit()
        self.db.refresh(inv_model)
        self.db.refresh(movement_model)

        return {
            "inventory": self._to_entity(inv_model),
            "movement": self._movement_to_entity(movement_model),
        }

    def return_stock_atomic(self, product_codigo: str, quantity: int,
                            reason: str, reference_type: Optional[str] = None,
                            reference_id: Optional[str] = None) -> dict:
        """ATOMIC: Return stock + create movement in single transaction."""
        now = datetime.utcnow()

        # Check idempotency
        if reference_type and reference_id:
            existing = self.db.query(StockMovementModel).filter(
                StockMovementModel.reference_type == reference_type,
                StockMovementModel.reference_id == reference_id,
                StockMovementModel.product_codigo == product_codigo,
                StockMovementModel.type == MovementType.RETURN.value,
            ).first()
            if existing:
                raise ValueError(f"Devolução já registrada para {reference_type} #{reference_id} no produto {product_codigo}")

        # Get or create inventory
        inv_model = self.db.query(InventoryModel).filter(
            InventoryModel.product_codigo == product_codigo
        ).first()
        if not inv_model:
            inv_model = InventoryModel(
                product_codigo=product_codigo, quantity=0, minimum_quantity=0
            )
            self.db.add(inv_model)
            self.db.flush()

        balance_before = inv_model.quantity
        balance_after = balance_before + quantity

        # Update inventory
        inv_model.quantity = balance_after
        inv_model.updated_at = now

        # Create movement
        movement_model = StockMovementModel(
            product_codigo=product_codigo,
            type=MovementType.RETURN.value,
            quantity=quantity,
            reason=reason,
            reference_type=reference_type,
            reference_id=reference_id,
            balance_before=balance_before,
            balance_after=balance_after,
            created_at=now,
        )
        self.db.add(movement_model)

        # SINGLE COMMIT
        self.db.commit()
        self.db.refresh(inv_model)
        self.db.refresh(movement_model)

        return {
            "inventory": self._to_entity(inv_model),
            "movement": self._movement_to_entity(movement_model),
        }

    def update_minimum(self, product_codigo: str, minimum: int) -> Optional[Inventory]:
        model = self.db.query(InventoryModel).filter(
            InventoryModel.product_codigo == product_codigo
        ).first()
        if not model:
            return None
        model.minimum_quantity = minimum
        model.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)
