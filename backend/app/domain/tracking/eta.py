"""ETA simples e determinístico (Fase 7.1).

Sem provedor externo e sem API key: usa a velocidade média observada nos
últimos minutos do histórico (`driver_location_history`) e cai para uma
velocidade-padrão quando não há amostra suficiente. É o suficiente para o
operador enxergar "chega em ~12 min"; não substitui um roteador de trânsito.

Determinístico de propósito: tudo entra por parâmetro (`now`, pontos, limites),
então dá para testar sem relógio real nem rede.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence

from app.domain.delivery.driver import _haversine_km as haversine_km

# Velocidade urbana conservadora (moto, com paradas) quando não há histórico.
DEFAULT_SPEED_KMH = 28.0
MIN_SAMPLES_FOR_SPEED = 3
MIN_ELAPSED_S = 30
# Abaixo disso a "velocidade" é ruído de GPS parado, não deslocamento.
MIN_USABLE_SPEED_KMH = 1.0
MIN_ETA_SECONDS = 60

# Ponto do histórico: (latitude, longitude, recorded_at)
HistoryPoint = tuple[float, float, datetime]


@dataclass(frozen=True)
class EtaEstimate:
    distance_km: float
    speed_kmh: float
    eta_seconds: int
    eta_at: datetime
    #: "history" quando veio do trajeto, "default" no fallback.
    speed_source: str


def average_speed_kmh(
    points: Sequence[HistoryPoint],
    *,
    min_samples: int = MIN_SAMPLES_FOR_SPEED,
) -> Optional[float]:
    """Velocidade média (km/h) entre pontos consecutivos, ou `None` se escasso.

    Ignora intervalos com `dt <= 0` (pontos no mesmo instante ou fora de ordem)
    para não dividir por zero nem inflar a velocidade.
    """
    if len(points) < min_samples:
        return None

    total_km = 0.0
    total_s = 0.0
    for (lat1, lng1, t1), (lat2, lng2, t2) in zip(points, points[1:]):
        dt = (t2 - t1).total_seconds()
        if dt <= 0:
            continue
        total_km += haversine_km(lat1, lng1, lat2, lng2)
        total_s += dt

    if total_s < MIN_ELAPSED_S:
        return None
    speed = (total_km / total_s) * 3600.0
    return speed if speed > MIN_USABLE_SPEED_KMH else None


def estimate_eta(
    *,
    origin: tuple[float, float],
    destination: tuple[float, float],
    now: datetime,
    recent_points: Sequence[HistoryPoint] = (),
    default_speed_kmh: float = DEFAULT_SPEED_KMH,
) -> EtaEstimate:
    """ETA de `origin` até `destination` (linha reta) na velocidade observada."""
    distance = haversine_km(origin[0], origin[1], destination[0], destination[1])
    measured = average_speed_kmh(recent_points)
    speed = measured if measured else default_speed_kmh
    source = "history" if measured else "default"

    seconds = int(max(MIN_ETA_SECONDS, (distance / max(speed, 1.0)) * 3600))
    return EtaEstimate(
        distance_km=round(distance, 3),
        speed_kmh=round(speed, 1),
        eta_seconds=seconds,
        eta_at=now + timedelta(seconds=seconds),
        speed_source=source,
    )
