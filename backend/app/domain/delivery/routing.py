"""
Routing Provider Abstraction — FASE 14

Provider-agnostic interface for geocoding and route calculation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


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
    def calculate_route(self, _origin: GeoPoint, _destination: GeoPoint) -> Optional[RouteInfo]:
        """Calculate route between two points."""
        ...

    @abstractmethod
    def estimate_eta(self, _origin: GeoPoint, _destination: GeoPoint) -> Optional[int]:
        """Estimate delivery time in minutes."""
        ...


@dataclass
class GeocodeResult:
    """Geocoding de um LOGRADOURO (não de um número) — ADR-0004.

    `intersecoes` = vias que cruzam o logradouro, cada uma com o número de
    casa em que o cruzamento acontece (``{"nome": "Rua A", "numero": 121}``),
    em ordem crescente. É o insumo do "entre A e B" por número (D12): quem
    preenche é a etapa 6 (Overpass); vazio = triagem, nunca chute.
    """

    lat: float = 0.0
    lng: float = 0.0
    rua: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    cep: str = ""
    intersecoes: List[dict] = field(default_factory=list)


class GeocodingProvider(ABC):
    """Contrato de geocoding — promovido do seam de `geocode()` (ADR-0004).

    Diferente do `RoutingProvider.geocode(address)` (que devolve só um ponto,
    para rota), aqui o retorno é o logradouro ESTRUTURADO: o renomeador precisa
    de CEP e das interseções para montar "entre A e B" por número. Um segundo
    contrato de geocoding no domínio seria uma segunda verdade — este vive no
    mesmo módulo do seam original.
    """

    name = "base"

    @abstractmethod
    def geocode_street(self, rua: str, bairro: str = "", cidade: str = "", uf: str = "") -> Optional[GeocodeResult]:
        """Geocodifica um logradouro (sem número). None = não encontrado."""
        ...


class MockGeocodingProvider(GeocodingProvider):
    """Mock para dev/testes — sem internet, contável para provar cache-hit."""

    name = "mock"

    def __init__(self, resultado: Optional[GeocodeResult] = None, encontrado: bool = True):
        # `encontrado=False` = logradouro que o provedor NÃO conhece. É distinto
        # de "sem resultado customizado" (que devolve o ponto default): sem essa
        # distinção, `MockGeocodingProvider(None)` pareceria um miss e nunca seria.
        self._resultado = resultado
        self._encontrado = encontrado
        self.chamadas = 0

    def geocode_street(self, rua: str, bairro: str = "", cidade: str = "", uf: str = "") -> Optional[GeocodeResult]:
        self.chamadas += 1
        if not self._encontrado:
            return None
        if self._resultado is not None:
            return self._resultado
        return GeocodeResult(
            lat=-23.5505,
            lng=-46.6333,
            rua=rua,
            bairro=bairro,
            cidade=cidade or "São Paulo",
            uf=uf or "SP",
            cep="01000-000",
        )


class MockRoutingProvider(RoutingProvider):
    """Mock routing for tests — no internet needed."""

    def __init__(self, default_eta_minutes: int = 30, default_distance_km: float = 5.0):
        self._eta = default_eta_minutes
        self._distance = default_distance_km

    def geocode(self, address: str) -> Optional[GeoPoint]:
        return GeoPoint(lat=-23.5505, lng=-46.6333)  # São Paulo

    def calculate_route(self, _origin: GeoPoint, _destination: GeoPoint) -> Optional[RouteInfo]:
        return RouteInfo(
            distance_km=self._distance,
            duration_minutes=self._eta,
            eta_minutes=self._eta,
        )

    def estimate_eta(self, _origin: GeoPoint, _destination: GeoPoint) -> Optional[int]:
        return self._eta
