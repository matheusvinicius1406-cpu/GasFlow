"""
Driver Domain Entity — FASE 14

Driver identity, status, and availability.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum
import uuid


class DriverStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    OFFLINE = "OFFLINE"
    INACTIVE = "INACTIVE"


@dataclass
class DriverLocation:
    """Last known GPS location."""
    lat: float = 0.0
    lng: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    accuracy_meters: Optional[float] = None


@dataclass
class Driver:
    """Physical driver entity."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    name: str = ""
    phone: str = ""
    status: DriverStatus = DriverStatus.AVAILABLE
    active: bool = True
    vehicle_id: Optional[str] = None
    license_number: Optional[str] = None
    location: Optional[DriverLocation] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_available(self) -> bool:
        return self.active and self.status == DriverStatus.AVAILABLE

    def set_busy(self):
        self.status = DriverStatus.BUSY
        self.updated_at = datetime.utcnow()

    def set_available(self):
        self.status = DriverStatus.AVAILABLE
        self.updated_at = datetime.utcnow()

    def go_offline(self):
        self.status = DriverStatus.OFFLINE
        self.updated_at = datetime.utcnow()

    def deactivate(self):
        self.status = DriverStatus.INACTIVE
        self.active = False
        self.updated_at = datetime.utcnow()

    def update_location(self, lat: float, lng: float, accuracy: Optional[float] = None):
        self.location = DriverLocation(lat=lat, lng=lng, accuracy_meters=accuracy)
        self.updated_at = datetime.utcnow()

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "phone": self.phone,
            "status": self.status.value,
            "active": self.active,
            "vehicle_id": self.vehicle_id,
            "license_number": self.license_number,
            "has_location": self.location is not None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
