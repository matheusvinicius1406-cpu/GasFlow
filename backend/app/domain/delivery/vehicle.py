"""
Vehicle Domain Entity — FASE 14 + 16.5

Delivery vehicle with per-product capacity tracking.
Supports:
  - Per-product capacity (P13, Água 20L, etc.)
  - Current load tracking
  - Driver association
  - GPS location
  - Status management
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
import uuid

from app.domain.delivery.capacity import ProductCapacity, VehicleLoad


class VehicleStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    IN_USE = "IN_USE"
    MAINTENANCE = "MAINTENANCE"
    INACTIVE = "INACTIVE"


@dataclass
class VehicleLocation:
    """Last known GPS location of vehicle."""
    lat: float = 0.0
    lng: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    accuracy_meters: Optional[float] = None
    speed_kmh: Optional[float] = None
    heading: Optional[float] = None


@dataclass
class Vehicle:
    """Delivery vehicle with per-product capacity."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    plate: str = ""
    model: str = ""
    # Legacy capacity fields (kept for backward compat)
    capacity: int = 0
    capacity_unit: str = "CYLINDERS"
    # Per-product capacity
    load: VehicleLoad = field(default_factory=VehicleLoad)
    # Association
    assigned_driver_id: Optional[str] = None
    # Status
    status: VehicleStatus = VehicleStatus.AVAILABLE
    # Location
    location: Optional[VehicleLocation] = None
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_available(self) -> bool:
        return self.status == VehicleStatus.AVAILABLE

    @property
    def has_capacity(self) -> bool:
        """Check if vehicle has any free capacity across all products."""
        for cap in self.load.capacities.values():
            if cap.free_for_dispatch > 0:
                return True
        return False

    def can_carry_order(self, items: Dict[str, int]) -> bool:
        """Check if vehicle can carry all items in an order."""
        return self.load.can_carry_order(items)

    def reserve_order(self, items: Dict[str, int]) -> bool:
        """Reserve capacity for an order."""
        if not self.load.reserve_order(items):
            return False
        self.updated_at = datetime.utcnow()
        return True

    def unreserve_order(self, items: Dict[str, int]):
        """Release reservation for an order."""
        self.load.unreserve_order(items)
        self.updated_at = datetime.utcnow()

    def load_order(self, items: Dict[str, int]) -> bool:
        """Physically load items."""
        if not self.load.load_order(items):
            return False
        self.updated_at = datetime.utcnow()
        return True

    def unload_order(self, items: Dict[str, int]):
        """Unload items (delivery completed)."""
        self.load.unload_order(items)
        self.updated_at = datetime.utcnow()

    def add_product_capacity(self, product_codigo: str, product_name: str,
                             max_capacity: int, unit: str = "UN") -> ProductCapacity:
        """Add or update product capacity."""
        cap = self.load.add_product(product_codigo, product_name, max_capacity, unit)
        self.updated_at = datetime.utcnow()
        return cap

    def get_load_summary(self) -> Dict[str, dict]:
        """Get current load for display."""
        return {
            code: {
                "product": cap.product_name,
                "loaded": cap.current_load,
                "capacity": cap.max_capacity,
                "available": cap.available,
                "reserved": cap.reserved,
                "free": cap.free_for_dispatch,
            }
            for code, cap in self.load.capacities.items()
        }

    def set_in_use(self):
        self.status = VehicleStatus.IN_USE
        self.updated_at = datetime.utcnow()

    def set_available(self):
        self.status = VehicleStatus.AVAILABLE
        self.assigned_driver_id = None
        self.updated_at = datetime.utcnow()

    def set_maintenance(self):
        self.status = VehicleStatus.MAINTENANCE
        self.updated_at = datetime.utcnow()

    def update_location(self, lat: float, lng: float, accuracy: Optional[float] = None,
                        speed: Optional[float] = None, heading: Optional[float] = None):
        self.location = VehicleLocation(
            lat=lat, lng=lng, accuracy_meters=accuracy,
            speed_kmh=speed, heading=heading,
        )
        self.updated_at = datetime.utcnow()

    def to_dict(self):
        result = {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "plate": self.plate,
            "model": self.model,
            "capacity": self.capacity,
            "capacity_unit": self.capacity_unit,
            "status": self.status.value,
            "assigned_driver_id": self.assigned_driver_id,
            "has_capacity": self.has_capacity,
            "products": self.load.to_dict()["products"],
            "load_summary": self.get_load_summary(),
            "has_location": self.location is not None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if self.location:
            result["location"] = {
                "lat": self.location.lat,
                "lng": self.location.lng,
                "timestamp": self.location.timestamp.isoformat(),
                "accuracy_meters": self.location.accuracy_meters,
            }
        return result
