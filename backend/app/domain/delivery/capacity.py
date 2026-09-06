"""
Vehicle Capacity — Per-Product Capacity Model

Each vehicle supports a set of products with individual capacities.
Capacity is separate from current load (cargo).

Example:
  Vehicle ABC-1234
    P13 GLP: capacity=6, loaded=4, available=2
    ÁGUA 20L: capacity=10, loaded=7, available=3
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
import uuid


@dataclass
class ProductCapacity:
    """Capacity for a single product type on a vehicle."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    vehicle_id: str = ""
    product_codigo: str = ""  # References Product.codigo
    product_name: str = ""  # Snapshot for display
    max_capacity: int = 0  # Maximum units this vehicle can carry
    current_load: int = 0  # Currently loaded units
    reserved: int = 0  # Units reserved for assigned deliveries
    unit: str = "UN"  # UN, CYLINDERS, LITERS, KG

    @property
    def available(self) -> int:
        """Available capacity = max - loaded."""
        return max(0, self.max_capacity - self.current_load)

    @property
    def free_for_dispatch(self) -> int:
        """Free capacity for new assignments = max - loaded - reserved."""
        return max(0, self.max_capacity - self.current_load - self.reserved)

    def can_carry(self, quantity: int) -> bool:
        """Check if vehicle can carry additional quantity."""
        return self.free_for_dispatch >= quantity

    def reserve(self, quantity: int) -> bool:
        """Reserve capacity for a delivery. Returns False if insufficient."""
        if not self.can_carry(quantity):
            return False
        self.reserved += quantity
        return True

    def unreserve(self, quantity: int):
        """Release reserved capacity (e.g., delivery cancelled)."""
        self.reserved = max(0, self.reserved - quantity)

    def load(self, quantity: int) -> bool:
        """Move reserved to loaded (physical loading). Returns False if over capacity."""
        if self.current_load + quantity > self.max_capacity:
            return False
        self.current_load += quantity
        self.reserved = max(0, self.reserved - quantity)
        return True

    def unload(self, quantity: int):
        """Remove units from load (delivery completed)."""
        self.current_load = max(0, self.current_load - quantity)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "vehicle_id": self.vehicle_id,
            "product_codigo": self.product_codigo,
            "product_name": self.product_name,
            "max_capacity": self.max_capacity,
            "current_load": self.current_load,
            "reserved": self.reserved,
            "available": self.available,
            "free_for_dispatch": self.free_for_dispatch,
            "unit": self.unit,
        }


@dataclass
class VehicleLoad:
    """Complete load manifest for a vehicle."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    vehicle_id: str = ""
    capacities: Dict[str, ProductCapacity] = field(default_factory=dict)

    def get_capacity(self, product_codigo: str) -> Optional[ProductCapacity]:
        return self.capacities.get(product_codigo)

    def can_carry_order(self, items: Dict[str, int]) -> bool:
        """
        Check if vehicle can carry all items in an order.
        items: {product_codigo: quantity}
        """
        for product_codigo, quantity in items.items():
            cap = self.get_capacity(product_codigo)
            if not cap or not cap.can_carry(quantity):
                return False
        return True

    def reserve_order(self, items: Dict[str, int]) -> bool:
        """Reserve capacity for all items. Returns False if any insufficient."""
        # Pre-check
        if not self.can_carry_order(items):
            return False
        # Reserve all
        for product_codigo, quantity in items.items():
            cap = self.get_capacity(product_codigo)
            if cap:
                cap.reserve(quantity)
        return True

    def unreserve_order(self, items: Dict[str, int]):
        """Release all reservations for an order."""
        for product_codigo, quantity in items.items():
            cap = self.get_capacity(product_codigo)
            if cap:
                cap.unreserve(quantity)

    def load_order(self, items: Dict[str, int]) -> bool:
        """Physically load all items. Returns False if any over capacity."""
        for product_codigo, quantity in items.items():
            cap = self.get_capacity(product_codigo)
            if not cap or not cap.load(quantity):
                return False
        return True

    def unload_order(self, items: Dict[str, int]):
        """Unload all items (delivery completed)."""
        for product_codigo, quantity in items.items():
            cap = self.get_capacity(product_codigo)
            if cap:
                cap.unload(quantity)

    def add_product(
        self, product_codigo: str, product_name: str, max_capacity: int, unit: str = "UN"
    ) -> ProductCapacity:
        """Add or update product capacity."""
        if product_codigo in self.capacities:
            existing = self.capacities[product_codigo]
            existing.max_capacity = max_capacity
            existing.product_name = product_name
            existing.unit = unit
            return existing
        cap = ProductCapacity(
            vehicle_id=self.vehicle_id,
            product_codigo=product_codigo,
            product_name=product_name,
            max_capacity=max_capacity,
            unit=unit,
        )
        self.capacities[product_codigo] = cap
        return cap

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "vehicle_id": self.vehicle_id,
            "products": [c.to_dict() for c in self.capacities.values()],
        }
