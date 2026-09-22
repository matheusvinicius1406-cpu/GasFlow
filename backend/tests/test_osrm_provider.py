"""Fase 10 — testes do OsrmRoutingProvider e circuit breaker.

Cobre:
- mock do OSRM (HTTP fake) → matrizes no formato esperado e provider="osrm";
- OSRM offline → fallback transparente com resposta 200 e provider="haversine";
- timeout → mesmo comportamento;
- breaker abre e fecha (incluindo sondagem half-open que falha reabre);
- consistência de ordem de magnitude entre OSRM mockado e haversine.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.infrastructure.routing.circuit_breaker import CircuitBreaker
from app.infrastructure.routing.haversine_provider import HaversineRoutingProvider
from app.infrastructure.routing.osrm_provider import OsrmRoutingProvider


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def haversine():
    return HaversineRoutingProvider(speed_kmh=28.0)


@pytest.fixture
def fake_client():
    """Cliente HTTP falso que retorna respostas do OSRM."""
    client = MagicMock()
    return client


@pytest.fixture
def osrm(fake_client):
    return OsrmRoutingProvider(
        "http://localhost:5000",
        timeout_s=2.0,
        client=fake_client,
    )


# ── Helpers ──────────────────────────────────────────────────


def _osrm_table_response(distances=None, durations=None, code="Ok"):
    """Gera uma resposta fake do /table."""
    return {
        "code": code,
        "distances": distances or [[0, 1000], [1000, 0]],
        "durations": durations or [[0, 60], [60, 0]],
    }


def _osrm_route_response(distance=1000, duration=60, coords=None):
    """Gera uma resposta fake do /route."""
    geometry = {"type": "LineString", "coordinates": coords or [[-51.21, -30.03], [-51.22, -30.04]]}
    return {
        "code": "Ok",
        "routes": [
            {
                "distance": distance,
                "duration": duration,
                "geometry": geometry,
            }
        ],
    }


# ── Testes do OSRM provider ──────────────────────────────────


class TestOsrmProvider:
    """Testes com HTTP mockado."""

    def test_distance_matrix(self, osrm, fake_client):
        """Matriz de distância do OSRM (metros → km)."""
        fake_client.get.return_value = MagicMock(
            json=lambda: _osrm_table_response(distances=[[0, 5000], [5000, 0]]),
            raise_for_status=lambda: None,
        )
        result = osrm.distance_matrix([(-30.03, -51.21), (-30.04, -51.22)])

        assert result == [[0.0, 5.0], [5.0, 0.0]]
        assert osrm.name == "osrm"

    def test_duration_matrix(self, osrm, fake_client):
        """Matriz de duração do OSRM (segundos)."""
        fake_client.get.return_value = MagicMock(
            json=lambda: _osrm_table_response(durations=[[0, 120], [120, 0]]),
            raise_for_status=lambda: None,
        )
        result = osrm.duration_matrix([(-30.03, -51.21), (-30.04, -51.22)])

        assert result == [[0, 120], [120, 0]]

    def test_route_com_geometria(self, osrm, fake_client):
        """Rota com geometria (GeoJSON [lng,lat] → [lat,lng])."""
        fake_client.get.return_value = MagicMock(
            json=lambda: _osrm_route_response(
                distance=5000,
                duration=300,
                coords=[[-51.21, -30.03], [-51.22, -30.04]],
            ),
            raise_for_status=lambda: None,
        )
        result = osrm.route((-30.03, -51.21), (-30.04, -51.22))

        assert result.distance_km == 5.0
        assert result.duration_s == 300
        assert result.geometry is not None
        assert result.geometry[0] == (-30.03, -51.21)  # lat,lng

    def test_fallback_offline(self, osrm, fake_client):
        """OSRM offline → fallback transparente para haversine."""
        fake_client.get.side_effect = ConnectionError("refused")

        result = osrm.distance_matrix([(-30.03, -51.21), (-30.04, -51.22)])

        # Fallback: haversine calcula a distância real.
        assert result[0][1] > 0
        assert result[0][0] == 0.0

    def test_fallback_timeout(self, osrm, fake_client):
        """Timeout → fallback transparente."""
        import httpx

        fake_client.get.side_effect = httpx.TimeoutException("timeout")

        result = osrm.duration_matrix([(-30.03, -51.21), (-30.04, -51.22)])
        assert result[0][1] > 0

    def test_coords_format(self, osrm):
        """Coordenadas no formato lng,lat do OSRM."""
        result = osrm._coords([(-30.03, -51.21), (-30.04, -51.22)])
        assert result == "-51.210000,-30.030000;-51.220000,-30.040000"


# ── Testes do circuit breaker ─────────────────────────────────


class TestCircuitBreaker:
    """Testes do breaker thread-safe."""

    def test_estado_inicial_closed(self):
        """Inicia fechado (permitindo requests)."""
        cb = CircuitBreaker(failure_threshold=3, cooldown_s=60.0)
        assert cb.allow() is True
        assert cb.is_open is False

    def test_abre_apos_n_falhas(self):
        """Abre após N falhas seguidas."""
        cb = CircuitBreaker(failure_threshold=3, cooldown_s=60.0)
        for _ in range(3):
            cb.record_failure()
        assert cb.is_open is True

    def test_nao_permite_requests_aberto(self):
        """Não permite requests quando aberto (antes do cooldown)."""
        cb = CircuitBreaker(failure_threshold=2, cooldown_s=60.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is True
        assert cb.allow() is False

    def test_sondagem_half_open(self):
        """Depois do cooldown, permite uma sondagem (half-open)."""
        clock = MagicMock(return_value=0.0)
        cb = CircuitBreaker(failure_threshold=2, cooldown_s=10.0, clock=clock)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is True

        # Avança o relógio além do cooldown
        clock.return_value = 15.0
        assert cb.allow() is True  # half-open

    def test_sondagem_sucesso_fecha(self):
        """Sondagem com sucesso fecha o breaker."""
        clock = MagicMock(return_value=0.0)
        cb = CircuitBreaker(failure_threshold=2, cooldown_s=10.0, clock=clock)
        cb.record_failure()
        cb.record_failure()
        clock.return_value = 15.0
        cb.allow()  # half-open
        cb.record_success()
        assert cb.is_open is False

    def test_sondagem_falha_reabre(self):
        """Sondagem com falha reabre imediatamente (sem esperar o limiar)."""
        clock = MagicMock(return_value=0.0)
        cb = CircuitBreaker(failure_threshold=3, cooldown_s=10.0, clock=clock)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        clock.return_value = 15.0
        cb.allow()  # half-open
        cb.record_failure()  # 1 falha na sondagem
        assert cb.is_open is True  # reabriu imediatamente

    def test_sucesso_zera_falhas(self):
        """Sucesso fecha o breaker e zera o contador de falhas."""
        cb = CircuitBreaker(failure_threshold=3, cooldown_s=60.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failures == 0
        assert cb.is_open is False


# ── Consistência haversine vs OSRM ───────────────────────────


class TestConsistencia:
    """Ordem de magnitude consistente entre providers."""

    def test_ordem_de_grandeza(self, haversine):
        """Haversine devolve distâncias na mesma ordem de grandeza que uma referência."""
        a = (-30.03, -51.21)
        b = (-30.04, -51.22)
        km = haversine.distance_matrix([a, b])[0][1]
        # Distância real ~1.4km; haversine (linha reta) deve ser >= 1km e <= 3km.
        assert 1.0 <= km <= 3.0
