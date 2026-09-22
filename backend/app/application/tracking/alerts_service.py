"""Alertas operacionais do rastreio (Fase 7.3).

Dois sinais, ambos calculados do **histórico** e do endereço da entrega:

- ``STALLED`` — entregador praticamente parado por mais de N minutos com uma
  entrega em rota (posição inicial e final dentro de um raio curto).
- ``DEVIATED`` — a posição atual está além do limiar de distância do endereço da
  entrega em andamento.

O serviço **não** envia nada: publica `driver.alert` no barramento realtime
existente (o roteamento por tenant/driver já é automático). Quem decide mostrar
banner/som é o painel.

Idempotência: quem chama avalia **uma vez por lote** de ingestão, não por ponto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.domain.delivery.driver import _haversine_km as haversine_km
from app.domain.events.event_bus import EventType, publish_driver_event
from app.infrastructure.repositories.delivery_persistence_repository import (
    SQLAlchemyDeliveryPersistenceRepository,
    SQLAlchemyDriverLocationRepository,
)

# Parado: menos que isso de deslocamento em `STALLED_MINUTES`.
STALLED_MINUTES = 10
STALLED_RADIUS_M = 60.0
# Desviado: distância até o endereço acima disso.
DEVIATION_KM = 1.2
STALLED_SAMPLE_LIMIT = 200


@dataclass(frozen=True)
class TrackingAlert:
    kind: str  # "STALLED" | "DEVIATED"
    driver_id: str
    delivery_id: Optional[str]
    detail: Dict[str, Any] = field(default_factory=dict)


class TrackingAlertsService:
    def __init__(self, db, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    def evaluate(
        self,
        *,
        driver_id: str,
        delivery_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> List[TrackingAlert]:
        """Avalia os sinais e publica `driver.alert` para cada um que disparar."""
        now = now or datetime.utcnow()

        if not delivery_id:
            active = SQLAlchemyDeliveryPersistenceRepository(self.db, tenant_id=self.tenant_id).find_active_delivery(
                driver_id
            )
            # Local `Any`: os modelos usam `Column(...)` legado, cuja leitura o
            # mypy tipa como `Column[Any]` (mesma convenção do repo).
            active_id: Any = active.delivery_id if active else None
            delivery_id = active_id

        alerts: List[TrackingAlert] = []
        stalled = self._check_stalled(driver_id=driver_id, delivery_id=delivery_id, now=now)
        if stalled:
            alerts.append(stalled)
        deviated = self._check_deviated(driver_id=driver_id, delivery_id=delivery_id)
        if deviated:
            alerts.append(deviated)

        for alert in alerts:
            publish_driver_event(
                EventType.DRIVER_ALERT,
                alert.driver_id,
                self.tenant_id,
                data={"kind": alert.kind, "delivery_id": alert.delivery_id, **alert.detail},
            )
        return alerts

    def _check_stalled(self, *, driver_id: str, delivery_id: Optional[str], now: datetime) -> Optional[TrackingAlert]:
        if not delivery_id:
            return None  # parado sem entrega em rota é descanso, não alerta

        repo = SQLAlchemyDriverLocationRepository(self.db)
        since = now - timedelta(minutes=STALLED_MINUTES)
        trail = repo.get_history(
            tenant_id=self.tenant_id,
            driver_id=driver_id,
            from_ts=since,
            to_ts=now,
            limit=STALLED_SAMPLE_LIMIT,
        )
        if len(trail) < 2:
            return None

        first, last = trail[0], trail[-1]
        first_lat: Any = first.latitude
        first_lng: Any = first.longitude
        last_lat: Any = last.latitude
        last_lng: Any = last.longitude
        moved_m = haversine_km(first_lat, first_lng, last_lat, last_lng) * 1000.0
        if moved_m > STALLED_RADIUS_M:
            return None
        return TrackingAlert(
            kind="STALLED",
            driver_id=driver_id,
            delivery_id=delivery_id,
            detail={"minutes": STALLED_MINUTES, "moved_m": round(moved_m, 1)},
        )

    def _check_deviated(self, *, driver_id: str, delivery_id: Optional[str]) -> Optional[TrackingAlert]:
        if not delivery_id:
            return None

        record = SQLAlchemyDeliveryPersistenceRepository(self.db, tenant_id=self.tenant_id).get_delivery(delivery_id)
        if not record or record.address_lat is None or record.address_lng is None:
            return None  # sem coordenadas do endereço não dá para afirmar desvio

        last = SQLAlchemyDriverLocationRepository(self.db).get_location(self.tenant_id, driver_id)
        if not last or last.latitude is None or last.longitude is None:
            return None

        last_lat: Any = last.latitude
        last_lng: Any = last.longitude
        addr_lat: Any = record.address_lat
        addr_lng: Any = record.address_lng
        deviation_km = haversine_km(last_lat, last_lng, addr_lat, addr_lng)
        if deviation_km <= DEVIATION_KM:
            return None
        return TrackingAlert(
            kind="DEVIATED",
            driver_id=driver_id,
            delivery_id=delivery_id,
            detail={"deviation_km": round(deviation_km, 2)},
        )
