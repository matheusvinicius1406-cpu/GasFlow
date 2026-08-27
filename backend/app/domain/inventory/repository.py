"""
Inventory Repository Interface — FASE 7.1

Atomic operations: single transaction for update + movement.
Idempotency: reference-based duplicate prevention.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
from app.domain.inventory.entity import Inventory
from app.domain.inventory.stock_movement import StockMovement


class InventoryRepository(ABC):
    """Abstract interface for inventory data access."""

    @abstractmethod
    def get_by_product(self, product_codigo: str) -> Optional[Inventory]:
        ...

    @abstractmethod
    def get_or_create(self, product_codigo: str, initial_quantity: int = 0) -> Inventory:
        ...

    @abstractmethod
    def list_all(self, stock_status: Optional[str] = None,
                 product_type: Optional[str] = None) -> List[Inventory]:
        ...

    @abstractmethod
    def add_stock_atomic(self, product_codigo: str, quantity: int,
                         reason: str, reference_type: Optional[str] = None,
                         reference_id: Optional[str] = None) -> dict:
        """ATOMIC: Add stock + create movement in single transaction."""
        ...

    @abstractmethod
    def deduct_stock_atomic(self, product_codigo: str, quantity: int,
                            reason: str, reference_type: Optional[str] = None,
                            reference_id: Optional[str] = None) -> dict:
        """ATOMIC: Deduct stock + create movement. Raises INSUFFICIENT_STOCK."""
        ...

    @abstractmethod
    def adjust_stock_atomic(self, product_codigo: str, new_quantity: int,
                            reason: str) -> dict:
        """ATOMIC: Adjust stock to exact quantity + create movement."""
        ...

    @abstractmethod
    def return_stock_atomic(self, product_codigo: str, quantity: int,
                            reason: str, reference_type: Optional[str] = None,
                            reference_id: Optional[str] = None) -> dict:
        """ATOMIC: Return stock + create movement."""
        ...

    @abstractmethod
    def update_minimum(self, product_codigo: str, minimum: int) -> Optional[Inventory]:
        ...

    @abstractmethod
    def get_movements(self, product_codigo: str,
                      page: int = 1, page_size: int = 20) -> Tuple[List[StockMovement], int]:
        ...

    @abstractmethod
    def get_movement_by_reference(self, reference_type: str,
                                  reference_id: str,
                                  product_codigo: Optional[str] = None,
                                  movement_type: Optional[str] = None) -> Optional[StockMovement]:
        ...

    @abstractmethod
    def has_movement_by_reference(self, reference_type: str,
                                  reference_id: str) -> bool:
        """Check if ANY movement exists for a given reference (any product/type)."""
        ...
