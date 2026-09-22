"""Contrato de roteamento por matriz (Fases 8–10).

NÃO confundir com `app/domain/delivery/routing.py` (FASE 14): aquele é o
provider *point-to-point* de geocoding/ETA do fluxo de pedido (e tem só mock).
Este contrato existe porque o **otimizador de sequência** (Fase 8) e o **score
de despacho** (Fase 9) precisam de matriz NxN, que aquele não oferece.

Duas implementações previstas:

- ``HaversineRoutingProvider`` — default, zero infra, em memória.
- ``OsrmRoutingProvider`` — opt-in via env, malha viária real (self-hosted).

O sistema funciona inteiro com a primeira. A segunda só troca precisão; nenhum
caminho de código pode *exigir* um provedor de malha viária.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

# (latitude, longitude) — mesma ordem usada no resto do domínio de entrega.
Point = tuple[float, float]


@dataclass(frozen=True)
class RouteLeg:
    """Rota entre dois pontos.

    ``geometry`` é opcional: um provedor em linha reta pode não ter uma
    geometria melhor que a própria sequência de pontos, e devolver `None` é
    mais honesto que inventar uma polyline de malha viária.
    """

    distance_km: float
    duration_s: int
    geometry: list[Point] | None = None


class RoutingProvider(ABC):
    """Contrato de roteamento.

    Toda implementação deve ser **total**: nunca levantar exceção para o
    chamador. Um provedor é uma otimização, não um caminho crítico — quando a
    fonte real cai, a implementação devolve o cálculo em linha reta.
    """

    #: Identificador do provedor, exposto na API (`provider`).
    name: str = "unknown"

    @abstractmethod
    def distance_matrix(self, points: Sequence[Point]) -> list[list[float]]:
        """Matriz NxN de distância em km entre todos os pares (mesma ordem)."""

    @abstractmethod
    def duration_matrix(self, points: Sequence[Point]) -> list[list[int]]:
        """Matriz NxN de duração em segundos (mesma ordem dos pontos)."""

    @abstractmethod
    def route(
        self,
        origin: Point,
        destination: Point,
        waypoints: Sequence[Point] = (),
    ) -> RouteLeg:
        """Rota entre dois pontos, passando por `waypoints` em ordem."""
