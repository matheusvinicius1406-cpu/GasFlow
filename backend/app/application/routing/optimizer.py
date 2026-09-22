"""Otimização de sequência de entregas (Fase 8).

Problema: dado um entregador com N entregas atribuídas (todas com coordenadas),
qual ordem minimiza a distância percorrida? Um TSP de caminho aberto, resolvido
com OR-Tools (Apache-2.0, self-hosted, sem conta nem limite de requisição).

Duas garantias de projeto:

1. **O import do OR-Tools é opcional.** Sem o wheel instalado, a ordem de
   atribuição é devolvida intacta e `provider="fallback"` denuncia o motivo.
   Nenhum caminho de código pode *exigir* o OR-Tools.
2. **Ganho pequeno não reordena.** Abaixo de `MIN_IMPROVEMENT_RATIO` a lista
   fica como está: trocar a ordem combinada com o entregador sem ganho real é
   ruído operacional, não otimização.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from app.domain.routing.provider import Point, RoutingProvider

logger = logging.getLogger("gasflow.routing.optimizer")

#: Ganho relativo mínimo para aceitar a reordenação (5%).
MIN_IMPROVEMENT_RATIO = 0.05

#: Teto de tempo do solver. A resposta é para o operador esperar na tela.
SOLVER_TIME_LIMIT_S = 1

#: Identificador devolvido quando o OR-Tools não está disponível.
FALLBACK_PROVIDER = "fallback"


@dataclass(frozen=True)
class OptimizedRoute:
    ordered_delivery_ids: list[str]
    total_distance_km: float
    total_duration_s: int
    geometry: list[Point] | None
    improvement_km: float
    provider: str


class DeliveryRouteOptimizer:
    """Reordena as entregas de um entregador para minimizar distância."""

    def __init__(self, provider: RoutingProvider):
        self._provider = provider

    # ── API ──────────────────────────────────────────────

    def optimize(
        self,
        *,
        origin: Point,
        deliveries: Sequence[tuple[str, float, float]],
        return_to_origin: bool = False,
    ) -> OptimizedRoute:
        """`deliveries` = [(delivery_id, latitude, longitude), ...] na ordem atual."""
        ids = [d[0] for d in deliveries]
        points = [(float(d[1]), float(d[2])) for d in deliveries]

        if not points:
            return OptimizedRoute([], 0.0, 0, None, 0.0, self._provider.name)

        nodes: list[Point] = [origin, *points]
        distances = self._provider.distance_matrix(nodes)
        durations = self._provider.duration_matrix(nodes)

        baseline_km, baseline_s = self._cost(list(range(1, len(points) + 1)), distances, durations, return_to_origin)

        # Zero ou uma entrega: não há o que reordenar (e a matriz seria 1x1).
        if len(points) < 2:
            return OptimizedRoute(
                ids,
                round(baseline_km, 3),
                baseline_s,
                self._polyline(points, origin, return_to_origin),
                0.0,
                self._provider.name,
            )

        order = self._solve(distances, len(points), return_to_origin)
        if order is None:
            return OptimizedRoute(
                ids,
                round(baseline_km, 3),
                baseline_s,
                self._polyline(points, origin, return_to_origin),
                0.0,
                FALLBACK_PROVIDER,
            )

        ordered_points = [points[i] for i in order]
        optimized_km, optimized_s = self._cost([i + 1 for i in order], distances, durations, return_to_origin)
        improvement = baseline_km - optimized_km
        gain_ratio = (improvement / baseline_km) if baseline_km > 0 else 0.0

        if improvement <= 0 or gain_ratio < MIN_IMPROVEMENT_RATIO:
            return OptimizedRoute(
                ids,
                round(baseline_km, 3),
                baseline_s,
                self._polyline(points, origin, return_to_origin),
                0.0,
                self._provider.name,
            )

        return OptimizedRoute(
            [ids[i] for i in order],
            round(optimized_km, 3),
            optimized_s,
            self._polyline(ordered_points, origin, return_to_origin),
            round(improvement, 3),
            self._provider.name,
        )

    # ── Custos ───────────────────────────────────────────

    @staticmethod
    def _cost(
        node_order: Sequence[int],
        distances: list[list[float]],
        durations: list[list[int]],
        return_to_origin: bool,
    ) -> tuple[float, int]:
        """Custo de percorrer `node_order` saindo do nó 0 (origem)."""
        total_km = 0.0
        total_s = 0
        previous = 0
        for node in node_order:
            total_km += distances[previous][node]
            total_s += durations[previous][node]
            previous = node
        if return_to_origin and node_order:
            total_km += distances[previous][0]
            total_s += durations[previous][0]
        return total_km, total_s

    @staticmethod
    def _polyline(points: Sequence[Point], origin: Point, return_to_origin: bool) -> list[Point]:
        sequence = [origin, *points]
        if return_to_origin and points:
            sequence.append(origin)
        return sequence

    # ── Solver ───────────────────────────────────────────

    def _solve(
        self,
        distances: list[list[float]],
        n_deliveries: int,
        return_to_origin: bool,
    ) -> list[int] | None:
        """Ordem ótima (índices 0-based das entregas). `None` = sem OR-Tools."""
        try:
            from ortools.constraint_solver import pywrapcp, routing_enums_pb2
        except ImportError:
            logger.info("routing.ortools_ausente — mantendo a ordem de atribuição")
            return None

        # Nós: 0 = origem, 1..N = entregas, e — quando a rota é aberta — um nó
        # final fictício de custo zero ("terminar em qualquer lugar"): é o jeito
        # padrão de modelar caminho sem retorno no OR-Tools.
        size = n_deliveries + 1 + (0 if return_to_origin else 1)
        matrix = [[0] * size for _ in range(size)]
        for i in range(n_deliveries + 1):
            for j in range(n_deliveries + 1):
                matrix[i][j] = int(round(distances[i][j] * 1000))  # km → metros

        manager = pywrapcp.RoutingIndexManager(size, 1, [0], [0 if return_to_origin else size - 1])
        routing = pywrapcp.RoutingModel(manager)

        def transit(from_index: int, to_index: int) -> int:
            return matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

        callback = routing.RegisterTransitCallback(transit)
        routing.SetArcCostEvaluatorOfAllVehicles(callback)

        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        params.time_limit.FromSeconds(SOLVER_TIME_LIMIT_S)
        params.log_search = False

        solution = routing.SolveWithParameters(params)
        if solution is None:
            logger.debug("routing.solver_sem_solucao — mantendo a ordem de atribuição")
            return None

        order: list[int] = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if 1 <= node <= n_deliveries:
                order.append(node - 1)
            index = solution.Value(routing.NextVar(index))

        # Solução parcial não é solução: melhor a ordem de atribuição inteira.
        if len(order) != n_deliveries:
            logger.debug("routing.solucao_parcial — mantendo a ordem de atribuição")
            return None
        return order
