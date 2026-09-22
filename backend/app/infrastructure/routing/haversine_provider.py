"""Provedor de roteamento em linha reta (default — zero infra, Fases 8–10)."""

from __future__ import annotations

from typing import Sequence

from app.core.config import settings
from app.domain.delivery.driver import _haversine_km
from app.domain.routing.provider import Point, RouteLeg, RoutingProvider


class HaversineRoutingProvider(RoutingProvider):
    """Distância haversine + duração por velocidade média configurável.

    É o default do sistema: não depende de serviço, rede nem conta. A distância
    devolvida é **linha reta** (portanto otimista em relação à malha viária) —
    quem precisa de precisão de rua liga o OSRM (Fase 10). Preferimos dizer isso
    a maquiar a estimativa com um fator de sinuosidade inventado.
    """

    name = "haversine"

    def __init__(self, speed_kmh: float | None = None):
        # 0 seria divisão por zero e velocidade absurda viraria duração 0.
        self._speed_kmh = max(float(speed_kmh or settings.routing_default_speed_kmh), 1.0)

    def _leg_km(self, a: Point, b: Point) -> float:
        return _haversine_km(a[0], a[1], b[0], b[1])

    def _seconds(self, km: float) -> int:
        return int(round((km / self._speed_kmh) * 3600.0))

    def distance_matrix(self, points: Sequence[Point]) -> list[list[float]]:
        n = len(points)
        matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                km = self._leg_km(points[i], points[j])
                matrix[i][j] = km
                matrix[j][i] = km
        return matrix

    def duration_matrix(self, points: Sequence[Point]) -> list[list[int]]:
        return [[self._seconds(km) for km in row] for row in self.distance_matrix(points)]

    def route(
        self,
        origin: Point,
        destination: Point,
        waypoints: Sequence[Point] = (),
    ) -> RouteLeg:
        sequence: list[Point] = [origin, *waypoints, destination]
        total_km = 0.0
        for a, b in zip(sequence, sequence[1:]):
            total_km += self._leg_km(a, b)
        return RouteLeg(
            distance_km=round(total_km, 6),
            duration_s=self._seconds(total_km),
            # A sequência já É a geometria possível em linha reta.
            geometry=sequence if len(sequence) > 2 else None,
        )
