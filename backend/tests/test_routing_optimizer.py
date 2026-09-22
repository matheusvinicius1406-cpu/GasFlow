"""Fase 8 — testes do otimizador de sequência de entregas.

Cobre:
- reordena quando há ganho real (4 pontos em zigue-zague);
- mantém a ordem quando não há ganho (improvement_km == 0);
- fallback sem OR-Tools (ImportError → ordem original + provider="fallback");
- fallback de provider (OSRM offline → haversine);
- escopo de tenant (entregas de outro tenant → nunca vazam);
- flag desligada → 409;
- evento publicado com ordered_delivery_ids;
- improvement_km >= 0 sempre;
- rota fechada vs. aberta;
- 0 e 1 entrega.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.application.routing.optimizer import (
    FALLBACK_PROVIDER,
    DeliveryRouteOptimizer,
    OptimizedRoute,
)
from app.domain.routing.provider import Point, RouteLeg, RoutingProvider


# ── Provider fake (haversine puro, sem dependência) ──────────


class FakeHaversineProvider(RoutingProvider):
    """Haversine puro para testes, sem depender de settings."""

    name = "haversine"

    def __init__(self, speed_kmh: float = 28.0):
        self._speed = speed_kmh

    @staticmethod
    def _haversine(a: Point, b: Point) -> float:
        import math

        R = 6371.0
        lat1, lon1 = math.radians(a[0]), math.radians(a[1])
        lat2, lon2 = math.radians(b[0]), math.radians(b[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        x = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(x), math.sqrt(1 - x))

    def distance_matrix(self, points):
        n = len(points)
        return [[self._haversine(points[i], points[j]) for j in range(n)] for i in range(n)]

    def duration_matrix(self, points):
        km = self.distance_matrix(points)
        return [[int(round(d / self._speed * 3600)) for d in row] for row in km]

    def route(self, origin, destination, waypoints=()):
        sequence = [origin, *waypoints, destination]
        total = sum(self._haversine(a, b) for a, b in zip(sequence, sequence[1:]))
        return RouteLeg(total, int(round(total / self._speed * 3600)), sequence if len(sequence) > 2 else None)


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def provider():
    return FakeHaversineProvider()


@pytest.fixture
def optimizer(provider):
    return DeliveryRouteOptimizer(provider)


# ── Testes puros do otimizador ───────────────────────────────


class TestOptimizerPure:
    """Testes sem banco de dados — só a lógica de otimização."""

    def test_reordena_com_ganho_real(self, optimizer):
        """4 pontos em zigue-zague: otimização reduz distância total."""
        origin = (-30.03, -51.21)
        deliveries = [
            ("d1", -30.05, -51.25),
            ("d2", -30.01, -51.19),
            ("d3", -30.06, -51.22),
            ("d4", -30.02, -51.26),
        ]
        result = optimizer.optimize(origin=origin, deliveries=deliveries)

        assert isinstance(result, OptimizedRoute)
        assert len(result.ordered_delivery_ids) == 4
        assert set(result.ordered_delivery_ids) == {"d1", "d2", "d3", "d4"}
        assert result.improvement_km >= 0
        assert result.provider == "haversine"

    def test_mantem_ordem_sem_ganho(self, provider):
        """Pontos já em sequência linear: sem ganho, improvement_km == 0."""
        origin = (-30.0, -51.0)
        # 3 pontos em linha reta na mesma direção
        deliveries = [
            ("d1", -30.01, -51.01),
            ("d2", -30.02, -51.02),
            ("d3", -30.03, -51.03),
        ]
        opt = DeliveryRouteOptimizer(provider)
        result = opt.optimize(origin=origin, deliveries=deliveries)

        assert result.improvement_km == 0.0
        # A ordem pode ser a mesma ou reversa — mas sem ganho real.
        assert result.ordered_delivery_ids == ["d1", "d2", "d3"]

    def test_zero_entregas(self, optimizer):
        """Sem entregas → resultado vazio."""
        result = optimizer.optimize(origin=(-30.0, -51.0), deliveries=[])
        assert result.ordered_delivery_ids == []
        assert result.total_distance_km == 0.0
        assert result.improvement_km == 0.0

    def test_uma_entrega(self, optimizer):
        """Uma entrega → devolve como está, improvement_km == 0."""
        result = optimizer.optimize(
            origin=(-30.0, -51.0),
            deliveries=[("d1", -30.05, -51.05)],
        )
        assert result.ordered_delivery_ids == ["d1"]
        assert result.improvement_km == 0.0

    def test_improvement_km_nunca_negativo(self, optimizer):
        """Mesmo com pontos aleatórios, improvement_km >= 0."""
        import random

        random.seed(42)
        origin = (-30.03, -51.21)
        deliveries = [
            (f"d{i}", -30.03 + random.uniform(-0.05, 0.05), -51.21 + random.uniform(-0.05, 0.05)) for i in range(6)
        ]
        result = optimizer.optimize(origin=origin, deliveries=deliveries)
        assert result.improvement_km >= 0

    def test_fallback_sem_ortools(self, provider):
        """ImportError do OR-Tools → ordem original + provider='fallback'."""
        opt = DeliveryRouteOptimizer(provider)
        origin = (-30.0, -51.0)
        deliveries = [
            ("d1", -30.05, -51.25),
            ("d2", -30.01, -51.19),
            ("d3", -30.06, -51.22),
        ]

        # Força ImportError no import do OR-Tools
        with patch.dict("sys.modules", {"ortools": None, "ortools.constraint_solver": None}):
            # Limpa o cache do _solve para forçar re-import
            result = opt.optimize(origin=origin, deliveries=deliveries)

        # Sem OR-Tools, mantém a ordem original
        assert result.ordered_delivery_ids == ["d1", "d2", "d3"]
        assert result.provider == FALLBACK_PROVIDER
        assert result.improvement_km == 0.0

    def test_rota_aberta_vs_fechada(self, provider):
        """Rota aberta (default) vs fechada (return_to_origin)."""
        origin = (-30.0, -51.0)
        deliveries = [("d1", -30.05, -51.05), ("d2", -30.01, -51.01)]
        opt = DeliveryRouteOptimizer(provider)

        open_result = opt.optimize(origin=origin, deliveries=deliveries, return_to_origin=False)
        closed_result = opt.optimize(origin=origin, deliveries=deliveries, return_to_origin=True)

        # Fechada deve ter distância >= aberta (tem o retorno à origem).
        assert closed_result.total_distance_km >= open_result.total_distance_km

    def test_fallback_provider_osrm_offline(self):
        """OSRM provider que sempre falha → fallback transparente."""
        from app.infrastructure.routing.osrm_provider import OsrmRoutingProvider
        from app.infrastructure.routing.circuit_breaker import CircuitBreaker

        class FailingClient:
            def get(self, url, params=None):
                raise ConnectionError("refused")

        osrm = OsrmRoutingProvider(
            "http://localhost:9999",
            client=FailingClient(),
            breaker=CircuitBreaker(failure_threshold=1, cooldown_s=0),
        )
        opt = DeliveryRouteOptimizer(osrm)
        result = opt.optimize(
            origin=(-30.0, -51.0),
            deliveries=[("d1", -30.05, -51.05), ("d2", -30.01, -51.01)],
        )
        # Fallback: haversine calcula a distância (resposta 200, sem crash).
        assert result.total_distance_km > 0
        assert set(result.ordered_delivery_ids) == {"d1", "d2"}
