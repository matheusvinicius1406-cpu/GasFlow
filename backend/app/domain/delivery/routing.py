"""
Routing Provider Abstraction — FASE 14

Provider-agnostic interface for geocoding and route calculation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class GeoPoint:
    lat: float = 0.0
    lng: float = 0.0


@dataclass
class RouteInfo:
    distance_km: float = 0.0
    duration_minutes: int = 0
    eta_minutes: int = 0


class RoutingProvider(ABC):
    """Abstract routing provider."""

    @abstractmethod
    def geocode(self, address: str) -> Optional[GeoPoint]:
        """Convert address to coordinates."""
        ...

    @abstractmethod
    def calculate_route(self, origin: GeoPoint, destination: GeoPoint) -> Optional[RouteInfo]:
        """Calculate route between two points."""
        ...

    @abstractmethod
    def estimate_eta(self, origin: GeoPoint, destination: GeoPoint) -> Optional[int]:
        """Estimate delivery time in minutes."""
        ...


class MockRoutingProvider(RoutingProvider):
    """Mock routing for tests — no internet needed."""

    def __init__(self, default_eta_minutes: int = 30, default_distance_km: float = 5.0):
        self._eta = default_eta_minutes
        self._distance = default_distance_km

    def geocode(self, address: str) -> Optional[GeoPoint]:
        return GeoPoint(lat=-23.5505, lng=-46.6333)  # São Paulo

    def calculate_route(self, origin: GeoPoint, destination: GeoPoint) -> Optional[RouteInfo]:
        return RouteInfo(
            distance_km=self._distance,
            duration_minutes=self._eta,
            eta_minutes=self._eta,
        )

    def estimate_eta(self, origin: GeoPoint, destination: GeoPoint) -> Optional[int]:
        return self._eta
