"""
Vehicle Domain Entity — FASE 14

Delivery vehicle with capacity tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum
import uuid


class VehicleStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    IN_USE = "IN_USE"
    MAINTENANCE = "MAINTENANCE"
    INACTIVE = "INACTIVE"


@dataclass
class Vehicle:
    """Delivery vehicle."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    plate: str = ""
    model: str = ""
    capacity: int = 0  # cylinders or load units
    capacity_unit: str = "CYLINDERS"
    status: VehicleStatus = VehicleStatus.AVAILABLE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_available(self) -> bool:
        return self.status == VehicleStatus.AVAILABLE

    def set_in_use(self):
        self.status = VehicleStatus.IN_USE
        self.updated_at = datetime.utcnow()

    def set_available(self):
        self.status = VehicleStatus.AVAILABLE
        self.updated_at = datetime.utcnow()

    def set_maintenance(self):
        self.status = VehicleStatus.MAINTENANCE
        self.updated_at = datetime.utcnow()

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "plate": self.plate,
            "model": self.model,
            "capacity": self.capacity,
            "capacity_unit": self.capacity_unit,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
