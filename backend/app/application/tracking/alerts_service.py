"""Alertas operacionais do rastreio (Parte 1 — fixes 1 e 2).

Dois sinais, ambos calculados do **histórico** e do endereço da entrega:

- ``STALLED`` — entregador praticamente parado por mais de N minutos com uma
  entrega em rota (posição inicial e final dentro de um raio curto).
- ``DEVIATED`` — a posição atual está além do limiar de distância do endereço da
  entrega **e** as condições de contexto valem (ver abaixo).

Correções desta versão:

1. **Cooldown de 15 min por `(tenant, driver, kind)`**, persistido em
   `tracking_alert_state`. Antes o alerta era republicado a cada lote de
   ingestão — 10 s depois o operador recebia outro igual, o dia inteiro.
2. **Reset do cooldown quando o entregador volta a se mover** (> 200 m): se
   parou, andou e parou de novo, é um evento novo, não repetição.
3. **`DEVIATED` com gate de contexto**: só em `EN_ROUTE`, só a menos de 3 km do
   destino (evita o falso positivo clássico da volta ao depósito) e só acima do
   limiar de desvio.

O serviço **não** envia nada: publica `driver.alert` no barramento realtime
existente. Quem decide mostrar banner/som é o painel.

Idempotência: quem chama avalia **uma vez por lote** de ingestão, não por ponto;
e mesmo chamando de novo, o cooldown segura a republicação.
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
    SQLAlchemyTrackingAlertRepository,
)

# Parado: menos que isso de deslocamento em `STALLED_MINUTES`.
STALLED_MINUTES = 10
STALLED_RADIUS_M = 60.0
# Se ele se moveu mais que isso, o cooldown do STALLED é zerado (evento novo).
STALLED_RESET_MOVE_M = 200.0
# Desviado: distância até o endereço acima disso.
DEVIATION_KM = 1.2
# Só considera desvio quando já está perto do destino: na volta do depósito a
# distância até o endereço é grande por definição, não por erro do entregador.
DEVIATION_PROXIMITY_KM = 3.0
# Janela mínima entre dois alertas do mesmo tipo para o mesmo entregador.
ALERT_COOLDOWN_MINUTES = 15
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
        """Avalia os sinais e publica `driver.alert` para cada um que disparar.

        Devolve **apenas** os alertas efetivamente publicados (um alerta dentro do
        cooldown não entra na lista).
        """
        now = now or datetime.utcnow()

        if not delivery_id:
            active = SQLAlchemyDeliveryPersistenceRepository(self.db, tenant_id=self.tenant_id).find_active_delivery(
                driver_id
            )
            # Local `Any`: os modelos usam `Column(...)` legado, cuja leitura o
            # mypy tipa como `Column[Any]` (mesma convenção do repo).
            active_id: Any = active.delivery_id if active else None
            delivery_id = active_id

        candidates: List[TrackingAlert] = []
        stalled = self._check_stalled(driver_id=driver_id, delivery_id=delivery_id, now=now)
        if stalled:
            candidates.append(stalled)
        deviated = self._check_deviated(driver_id=driver_id, delivery_id=delivery_id)
        if deviated:
            candidates.append(deviated)

        published: List[TrackingAlert] = []
        for alert in candidates:
            if not self._cooldown_allows(driver_id=alert.driver_id, kind=alert.kind, now=now):
                continue
            publish_driver_event(
                EventType.DRIVER_ALERT,
                alert.driver_id,
                self.tenant_id,
                data={"kind": alert.kind, "delivery_id": alert.delivery_id, **alert.detail},
            )
            self._alert_repo().mark_sent(
                tenant_id=self.tenant_id,
                driver_id=alert.driver_id,
                kind=alert.kind,
                sent_at=now,
            )
            published.append(alert)
        return published

    # ── Cooldown ────────────────────────────────────────────

    def _alert_repo(self) -> SQLAlchemyTrackingAlertRepository:
        return SQLAlchemyTrackingAlertRepository(self.db)

    def _cooldown_allows(self, *, driver_id: str, kind: str, now: datetime) -> bool:
        last_sent = self._alert_repo().get_last_sent_at(self.tenant_id, driver_id, kind)
        if last_sent is None:
            return True
        return (now - last_sent) >= timedelta(minutes=ALERT_COOLDOWN_MINUTES)

    # ── Sinais ──────────────────────────────────────────────

    def _check_stalled(self, *, driver_id: str, delivery_id: Optional[str], now: datetime) -> Optional[TrackingAlert]:
        if not delivery_id:
            return None  # parado sem entrega em rota é descanso, não alerta

        trail = self._recent_trail(driver_id=driver_id, now=now)
        if len(trail) < 2:
            return None

        first, last = trail[0], trail[-1]
        moved_m = self._distance_m(first, last)

        # Voltou a se mover: o próximo parado é um evento novo — zera o cooldown.
        if moved_m > STALLED_RESET_MOVE_M:
            self._alert_repo().clear_kind(self.tenant_id, driver_id, "STALLED")
            return None
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
        if str(record.status) != "EN_ROUTE":
            return None  # nos outros status ainda não há rota a desviar

        last = SQLAlchemyDriverLocationRepository(self.db).get_location(self.tenant_id, driver_id)
        if not last or last.latitude is None or last.longitude is None:
            return None

        deviation_km = self._distance_km(last, record)
        if deviation_km <= DEVIATION_KM:
            return None
        if deviation_km > DEVIATION_PROXIMITY_KM:
            # Longe do destino por definição (ex.: acabou de sair do depósito ou
            # o endereço é noutra região): não é desvio, é o começo do trajeto.
            return None

        return TrackingAlert(
            kind="DEVIATED",
            driver_id=driver_id,
            delivery_id=delivery_id,
            detail={"deviation_km": round(deviation_km, 2)},
        )

    # ── Helpers ─────────────────────────────────────────────

    def _recent_trail(self, *, driver_id: str, now: datetime):
        repo = SQLAlchemyDriverLocationRepository(self.db)
        return repo.get_history(
            tenant_id=self.tenant_id,
            driver_id=driver_id,
            from_ts=now - timedelta(minutes=STALLED_MINUTES),
            to_ts=now,
            limit=STALLED_SAMPLE_LIMIT,
        )

    def _distance_m(self, first, last) -> float:
        a_lat: Any = first.latitude
        a_lng: Any = first.longitude
        b_lat: Any = last.latitude
        b_lng: Any = last.longitude
        return haversine_km(a_lat, a_lng, b_lat, b_lng) * 1000.0

    def _distance_km(self, location, record) -> float:
        loc_lat: Any = location.latitude
        loc_lng: Any = location.longitude
        addr_lat: Any = record.address_lat
        addr_lng: Any = record.address_lng
        return haversine_km(loc_lat, loc_lng, addr_lat, addr_lng)
