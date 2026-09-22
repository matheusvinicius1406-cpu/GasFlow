"""Implementações e seleção de provedores de roteamento (Fases 8–10)."""

from app.infrastructure.routing.factory import get_routing_provider
from app.infrastructure.routing.haversine_provider import HaversineRoutingProvider

__all__ = ["HaversineRoutingProvider", "get_routing_provider"]
