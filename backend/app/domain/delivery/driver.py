"""
Driver Domain Entity — FASE 14 + 16.5

Driver identity, status, availability, GPS tracking, and load association.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
import uuid


class DriverStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    OFFLINE = "OFFLINE"
    PAUSED = "PAUSED"
    UNAVAILABLE = "UNAVAILABLE"
    INACTIVE = "INACTIVE"


class PauseReason(str, Enum):
    LUNCH = "LUNCH"
    FUEL = "FUEL"
    MAINTENANCE = "MAINTENANCE"
    PERSONAL = "PERSONAL"
    OTHER = "OTHER"


@dataclass
class DriverLocation:
    """GPS location with metadata."""

    lat: float = 0.0
    lng: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    accuracy_meters: Optional[float] = None
    speed_kmh: Optional[float] = None
    heading: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lat": self.lat,
            "lng": self.lng,
            "timestamp": self.timestamp.isoformat(),
            "accuracy_meters": self.accuracy_meters,
            "speed_kmh": self.speed_kmh,
            "heading": self.heading,
        }


@dataclass
class DriverMetrics:
    """Operational metrics for a driver."""

    total_deliveries: int = 0
    completed_deliveries: int = 0
    failed_deliveries: int = 0
    today_deliveries: int = 0
    today_completed: int = 0
    today_distance_km: float = 0.0
    avg_delivery_minutes: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_deliveries": self.total_deliveries,
            "completed_deliveries": self.completed_deliveries,
            "failed_deliveries": self.failed_deliveries,
            "today_deliveries": self.today_deliveries,
            "today_completed": self.today_completed,
            "today_distance_km": round(self.today_distance_km, 2),
            "avg_delivery_minutes": round(self.avg_delivery_minutes, 1),
        }


@dataclass
class Driver:
    """Physical driver entity with full operational support."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    name: str = ""
    phone: str = ""
    status: DriverStatus = DriverStatus.AVAILABLE
    active: bool = True
    # Vehicle
    vehicle_id: Optional[str] = None
    license_number: Optional[str] = None
    # Location
    location: Optional[DriverLocation] = None
    last_seen: Optional[datetime] = None
    # Pause
    pause_reason: Optional[PauseReason] = None
    paused_at: Optional[datetime] = None
    # Metrics
    metrics: DriverMetrics = field(default_factory=DriverMetrics)
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_available(self) -> bool:
        return self.active and self.status == DriverStatus.AVAILABLE

    @property
    def is_online(self) -> bool:
        return self.status not in {DriverStatus.OFFLINE, DriverStatus.INACTIVE}

    @property
    def is_paused(self) -> bool:
        return self.status == DriverStatus.PAUSED

    def set_available(self):
        self.status = DriverStatus.AVAILABLE
        self.pause_reason = None
        self.paused_at = None
        self.updated_at = datetime.utcnow()

    def set_busy(self):
        self.status = DriverStatus.BUSY
        self.updated_at = datetime.utcnow()

    def go_offline(self):
        self.status = DriverStatus.OFFLINE
        self.updated_at = datetime.utcnow()

    def pause(self, reason: PauseReason = PauseReason.OTHER):
        """Driver pauses (e.g., lunch, fuel). Cannot pause if delivering."""
        self.status = DriverStatus.PAUSED
        self.pause_reason = reason
        self.paused_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def resume(self):
        """Driver resumes from pause."""
        self.set_available()

    def deactivate(self):
        self.status = DriverStatus.INACTIVE
        self.active = False
        self.updated_at = datetime.utcnow()

    def update_location(
        self,
        lat: float,
        lng: float,
        accuracy: Optional[float] = None,
        speed: Optional[float] = None,
        heading: Optional[float] = None,
    ):
        self.location = DriverLocation(
            lat=lat,
            lng=lng,
            accuracy_meters=accuracy,
            speed_kmh=speed,
            heading=heading,
        )
        self.last_seen = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def distance_to(self, lat: float, lng: float) -> float:
        """Calculate approximate distance to a point in km (Haversine)."""
        if not self.location:
            return float("inf")
        return _haversine_km(self.location.lat, self.location.lng, lat, lng)

    def to_dict(self):
        result = {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "phone": self.phone,
            "status": self.status.value,
            "active": self.active,
            "vehicle_id": self.vehicle_id,
            "license_number": self.license_number,
            "is_available": self.is_available,
            "is_online": self.is_online,
            "pause_reason": self.pause_reason.value if self.pause_reason else None,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "has_location": self.location is not None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "metrics": self.metrics.to_dict(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if self.location:
            result["location"] = self.location.to_dict()
        return result


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in km between two GPS points."""
    import math

    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c
