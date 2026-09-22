"""Serviço de ETA do entregador (Fase 7.1).

Lê a última posição (`driver_locations`) e a velocidade observada no histórico
recente (`driver_location_history`). Escopo sempre por `tenant_id` + `driver_id`.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.domain.tracking.eta import estimate_eta
from app.infrastructure.repositories.delivery_persistence_repository import (
    SQLAlchemyDriverLocationRepository,
)

# Janela de amostragem da velocidade observada.
ETA_WINDOW_MINUTES = 15
ETA_SAMPLE_LIMIT = 500


class DriverEtaService:
    """ETA do entregador até um destino, usando o histórico recente."""

    def __init__(self, db, tenant_id: str, window_minutes: int = ETA_WINDOW_MINUTES):
        self.db = db
        self.tenant_id = tenant_id
        self.window_minutes = window_minutes

    def eta_to(
        self,
        *,
        driver_id: str,
        destination: tuple[float, float],
        now: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """ETA até `destination` ou `None` quando não há posição conhecida."""
        now = now or datetime.utcnow()
        repo = SQLAlchemyDriverLocationRepository(self.db)

        last = repo.get_location(self.tenant_id, driver_id)
        if not last or last.latitude is None or last.longitude is None:
            return None

        since = now - timedelta(minutes=self.window_minutes)
        trail = repo.get_history(
            tenant_id=self.tenant_id,
            driver_id=driver_id,
            from_ts=since,
            to_ts=now,
            limit=ETA_SAMPLE_LIMIT,
        )
        # Locais `Any` de propósito: os modelos usam `Column(...)` legado, cuja
        # leitura o mypy tipa como `Column[Any]` (mesma convenção do repo).
        origin_lat: Any = last.latitude
        origin_lng: Any = last.longitude
        samples: List[tuple] = [(p.latitude, p.longitude, p.recorded_at) for p in trail]

        estimate = estimate_eta(
            origin=(origin_lat, origin_lng),
            destination=destination,
            now=now,
            recent_points=samples,
        )
        return {
            "driver_id": driver_id,
            "origin": {"latitude": origin_lat, "longitude": origin_lng},
            "destination": {"latitude": destination[0], "longitude": destination[1]},
            "distance_km": estimate.distance_km,
            "speed_kmh": estimate.speed_kmh,
            "speed_source": estimate.speed_source,
            "eta_seconds": estimate.eta_seconds,
            "eta_at": estimate.eta_at.isoformat(),
            "position_age_seconds": int((now - last.timestamp).total_seconds()) if last.timestamp else None,
        }
