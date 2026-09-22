"""Provedor OSRM (opt-in, self-hosted — Fase 10).

Nada aqui é caminho crítico: todo método é **total** e cai para o cálculo em
linha reta quando o OSRM não responde, responde mal ou está com o breaker
aberto. Deploy em `docs/routing/osrm.md`; ativação por env (`ROUTING_PROVIDER`
+ `OSRM_BASE_URL`).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, Sequence

import httpx

from app.core.config import settings
from app.domain.routing.provider import Point, RouteLeg, RoutingProvider
from app.infrastructure.routing.circuit_breaker import CircuitBreaker
from app.infrastructure.routing.haversine_provider import HaversineRoutingProvider

logger = logging.getLogger("gasflow.routing.osrm")


class _HttpClient(Protocol):
    """Só o suficiente para injetar um fake nos testes."""

    def get(self, url: str, params: dict[str, str] | None = ...) -> Any: ...


class OsrmRoutingProvider(RoutingProvider):
    """Matrizes e rotas reais via OSRM, com fallback transparente."""

    name = "osrm"

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float | None = None,
        breaker: CircuitBreaker | None = None,
        fallback: RoutingProvider | None = None,
        client: _HttpClient | None = None,
    ):
        self._base = base_url.rstrip("/")
        self._timeout = float(timeout_s if timeout_s is not None else settings.osrm_timeout_seconds)
        self._breaker = breaker or CircuitBreaker(
            settings.osrm_breaker_failures,
            settings.osrm_breaker_cooldown_s,
        )
        self._fallback = fallback or HaversineRoutingProvider()
        self._client = client

    # ── HTTP ─────────────────────────────────────────────

    def _fetch(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        if self._client is not None:
            response = self._client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _coords(points: Sequence[Point]) -> str:
        # OSRM usa longitude,latitude — o inverso do nosso Point.
        return ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in points)

    def _guard(self, request: Any) -> Any:
        """Executa a chamada protegida pelo breaker. `None` = indisponível."""
        if not self._breaker.allow():
            logger.debug("osrm.breaker_open — usando fallback local")
            return None
        was_open = self._breaker.is_open
        try:
            result = request()
        except Exception:
            self._breaker.record_failure()
            if self._breaker.is_open and not was_open:
                logger.warning("osrm.unavailable — caindo para haversine (breaker aberto)")
            else:
                logger.debug("osrm.request_failed", exc_info=True)
            return None
        self._breaker.record_success()
        return result

    # ── Contrato ─────────────────────────────────────────

    def _table(self, points: list[Point], annotation: str) -> list[list[float]] | None:
        """Matriz crua do OSRM (`distances` em m ou `durations` em s)."""

        def request() -> list[list[float]]:
            url = f"{self._base}/table/v1/driving/{self._coords(points)}"
            payload = self._fetch(url, {"annotations": annotation})
            if payload.get("code") not in (None, "Ok"):
                raise ValueError(f"osrm recusou a matriz: {payload.get('code')}")
            raw = payload.get(annotation)
            if not isinstance(raw, list):
                raise ValueError(f"osrm sem '{annotation}' na resposta")
            return raw

        return self._guard(request)

    def distance_matrix(self, points: Sequence[Point]) -> list[list[float]]:
        pts = list(points)
        if not pts:
            return []
        raw = self._table(pts, "distances")
        if raw is None:
            return self._fallback.distance_matrix(pts)
        return [[float(value) / 1000.0 for value in row] for row in raw]

    def duration_matrix(self, points: Sequence[Point]) -> list[list[int]]:
        pts = list(points)
        if not pts:
            return []
        raw = self._table(pts, "durations")
        if raw is None:
            return self._fallback.duration_matrix(pts)
        return [[int(round(float(value))) for value in row] for row in raw]

    def route(
        self,
        origin: Point,
        destination: Point,
        waypoints: Sequence[Point] = (),
    ) -> RouteLeg:
        pts = [origin, *waypoints, destination]

        def request() -> RouteLeg:
            url = f"{self._base}/route/v1/driving/{self._coords(pts)}"
            payload = self._fetch(
                url,
                {"overview": "full", "geometries": "geojson", "steps": "false"},
            )
            if payload.get("code") not in (None, "Ok"):
                raise ValueError(f"osrm recusou a rota: {payload.get('code')}")
            routes = payload.get("routes") or []
            if not routes:
                raise ValueError("osrm sem rotas na resposta")
            best = routes[0]
            geometry: list[Point] | None = None
            coords = ((best.get("geometry") or {}).get("coordinates")) or []
            if coords:
                # GeoJSON devolve [lng, lat]; o domínio usa (lat, lng).
                geometry = [(float(lat), float(lng)) for lng, lat in coords]
            return RouteLeg(
                distance_km=float(best["distance"]) / 1000.0,
                duration_s=int(round(float(best["duration"]))),
                geometry=geometry,
            )

        leg = self._guard(request)
        if leg is None:
            return self._fallback.route(origin, destination, waypoints)
        return leg
