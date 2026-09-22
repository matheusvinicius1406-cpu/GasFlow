"""Score de despacho (Fase 9).

Extrai o score que hoje vive inline no `/delivery/dispatch/suggest` para um
módulo testável e o enriquece com dados que o cálculo atual não olha:
posição vinda do **histórico** (não do upsert congelado), prazo da entrega e
fairness na janela recente.

O motor antigo (`app/domain/delivery/dispatch_engine.py`) **não** é reescrito:
com a flag desligada, `/dispatch/suggest` continua chamando `DispatchEngine` e
o comportamento é idêntico ao de antes.

Componentes (pesos por env — ver `dispatch_weight_*`):

- ``proximity``  — distância real até o endereço, via ``RoutingProvider``.
  Posição velha (> `STALE_POSITION_MINUTES`) vale menos; sem posição, zero.
- ``load``       — entregas ativas do entregador contra `LOAD_FULL_DELIVERIES`.
- ``deadline``   — ETA até o endereço contra `scheduled_at`. Sem prazo, neutro.
- ``fairness``   — penaliza quem recebeu muitas entregas na janela recente.

``vehicle_fit`` está deliberadamente **fora**: o encaixe de carga por produto já
é um gate de *elegibilidade* (via `DriverStockService` + `filter_candidate`)
antes do score, e repetir isso como pontuação contaria a mesma coisa duas vezes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from app.core.config import settings
from app.domain.routing.provider import Point, RoutingProvider
from app.infrastructure.routing.factory import get_routing_provider

logger = logging.getLogger("gasflow.dispatch.scorer")

#: Saturação da proximidade: 5 km zera o componente (mesma régua do motor atual).
PROXIMITY_KM_SATURATION = 20.0

#: Acima disso a posição é "velha" e a proximidade vale `STALE_POSITION_FACTOR`.
STALE_POSITION_MINUTES = 15
STALE_POSITION_FACTOR = 0.85

#: Entregas ativas que consideramos "cheio" para uma moto.
LOAD_FULL_DELIVERIES = 4.0

#: Penalidade de atraso: 10 min de atraso no ETA zeram o componente.
DEADLINE_PENALTY_PER_MINUTE = 10.0

#: Fairness: cada entrega atribuída na janela desconta este tanto.
FAIRNESS_WINDOW_HOURS = 4.0
FAIRNESS_PENALTY_PER_DELIVERY = 20.0

#: Pesos default — usados quando a env não define nada utilizável.
DEFAULT_WEIGHTS = {
    "proximity": 0.45,
    "load": 0.25,
    "deadline": 0.20,
    "fairness": 0.10,
}

#: Status em que o entregador está de fato em rota (mesma lista do repositório).
ACTIVE_ROUTING_STATUSES = ("ASSIGNED", "DISPATCHED", "EN_ROUTE")

COMPONENTS = ("proximity", "load", "deadline", "fairness")


@dataclass(frozen=True)
class DispatchScore:
    """Score de um entregador candidato para uma entrega."""

    driver_id: str
    driver_name: str
    total: float
    breakdown: Dict[str, float]
    reasons: List[str] = field(default_factory=list)
    distance_km: float = 0.0
    active_deliveries: int = 0
    position_age_s: Optional[int] = None
    has_recent_position: bool = False


class DispatchScorer:
    """Ranqueia entregadores para uma entrega. Somente leitura."""

    def __init__(
        self,
        db: Any,
        tenant_id: str,
        provider: Optional[RoutingProvider] = None,
        now: Optional[datetime] = None,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self._provider = provider or get_routing_provider()
        self._now = now
        self._weights = self._resolve_weights()

    # ── API ──────────────────────────────────────────────

    def score(
        self,
        *,
        delivery_id: str,
        candidate_driver_ids: Optional[Sequence[str]] = None,
    ) -> List[DispatchScore]:
        """Ranqueia os candidatos (melhor primeiro). Levanta `LookupError` sem entrega."""
        from app.infrastructure.repositories.delivery_persistence_repository import (
            SQLAlchemyDeliveryPersistenceRepository,
        )

        deliveries = SQLAlchemyDeliveryPersistenceRepository(self.db, self.tenant_id)
        delivery = deliveries.get_delivery(delivery_id)
        if delivery is None:
            raise LookupError(f"entrega {delivery_id} não encontrada")

        now = self._now or datetime.utcnow()
        since_fairness = now - timedelta(hours=FAIRNESS_WINDOW_HOURS)

        if candidate_driver_ids is None:
            candidates = [d.codigo for d in self._driver_repo().listar_todos() if d.ativo]
        else:
            candidates = list(candidate_driver_ids)

        scores: List[DispatchScore] = []
        for driver_id in candidates:
            scored = self._score_one(driver_id, delivery, deliveries, now, since_fairness)
            if scored is not None:  # inelegível (inativo/inexistente) não é "pior"
                scores.append(scored)

        # Desempate determinístico: dois scores iguais não podem trocar de ordem
        # entre duas chamadas — o operador vê a lista piscar.
        scores.sort(key=lambda s: (-s.total, s.driver_id))
        return scores

    # ── Internos ─────────────────────────────────────────

    def _driver_repo(self) -> Any:
        from app.infrastructure.repositories.delivery_repository import (
            SQLAlchemyDeliveryDriverRepository,
        )

        return SQLAlchemyDeliveryDriverRepository(self.db, self.tenant_id)

    def _score_one(
        self,
        driver_id: str,
        delivery: Any,
        deliveries: Any,
        now: datetime,
        since_fairness: datetime,
    ) -> Optional[DispatchScore]:
        model = self._driver_repo().find_by_id_as_model(driver_id)
        if model is None or not model.ativo:
            # Candidato inexistente ou inativo no tenant não é "pior", é inelegível.
            return None

        reasons: List[str] = []
        position, age_s = self._position(driver_id, now)
        destination: Optional[Point] = None
        if delivery.address_lat is not None and delivery.address_lng is not None:
            destination = (float(delivery.address_lat), float(delivery.address_lng))

        breakdown: Dict[str, float] = {}
        breakdown["proximity"], distance_km = self._proximity(position, age_s, destination, reasons)
        breakdown["load"], active = self._load(driver_id, deliveries, reasons)
        breakdown["deadline"] = self._deadline(delivery, position, destination, now, reasons)
        breakdown["fairness"] = self._fairness(driver_id, deliveries, since_fairness, reasons)

        total = round(sum(self._weights[name] * breakdown[name] for name in COMPONENTS), 2)
        return DispatchScore(
            driver_id=driver_id,
            driver_name=getattr(model, "nome", driver_id) or driver_id,
            total=total,
            breakdown={name: round(breakdown[name], 2) for name in COMPONENTS},
            reasons=reasons,
            distance_km=round(distance_km, 3),
            active_deliveries=active,
            position_age_s=age_s,
            has_recent_position=age_s is not None and age_s <= STALE_POSITION_MINUTES * 60,
        )

    def _position(self, driver_id: str, now: datetime) -> tuple[Optional[Point], Optional[int]]:
        """Posição mais recente do histórico; cai para o upsert se não houver."""
        from app.infrastructure.repositories.delivery_persistence_repository import (
            SQLAlchemyDriverLocationRepository,
        )

        repo = SQLAlchemyDriverLocationRepository(self.db)
        point = repo.latest_history_point(self.tenant_id, driver_id)
        if point is not None and point.latitude is not None and point.longitude is not None:
            age = None
            if point.recorded_at is not None:
                age = int((now - point.recorded_at).total_seconds())
            return (float(point.latitude), float(point.longitude)), age

        last = repo.get_location(self.tenant_id, driver_id)
        if last is not None and last.latitude is not None and last.longitude is not None:
            age = None
            if last.timestamp is not None:
                age = int((now - last.timestamp).total_seconds())
            return (float(last.latitude), float(last.longitude)), age
        return None, None

    def _proximity(
        self,
        position: Optional[Point],
        age_s: Optional[int],
        destination: Optional[Point],
        reasons: List[str],
    ) -> tuple[float, float]:
        if position is None:
            reasons.append("Sem posição conhecida — proximidade zerada")
            return 0.0, 0.0
        if destination is None:
            reasons.append("Entrega sem coordenadas — proximidade zerada")
            return 0.0, 0.0

        distance_km = self._provider.distance_matrix([position, destination])[0][1]
        score = max(0.0, 100.0 - distance_km * PROXIMITY_KM_SATURATION)
        if age_s is not None and age_s > STALE_POSITION_MINUTES * 60:
            score *= STALE_POSITION_FACTOR
            reasons.append(f"Posição de {age_s // 60} min atrás — proximidade descontada")
        elif distance_km <= 3.0:
            reasons.append(f"A {distance_km:.1f} km do endereço")
        return score, distance_km

    def _load(self, driver_id: str, deliveries: Any, reasons: List[str]) -> tuple[float, int]:
        counts = deliveries.count_by_driver(driver_id)
        active = sum(counts.get(status, 0) for status in ACTIVE_ROUTING_STATUSES)
        full = max(float(settings.dispatch_load_full_deliveries), 1.0)
        score = max(0.0, 100.0 * (1.0 - active / full))
        if active == 0:
            reasons.append("Sem entregas ativas")
        elif active >= full:
            reasons.append(f"⚠ {active} entregas ativas — capacidade cheia")
        else:
            reasons.append(f"{active} entrega(s) ativa(s)")
        return score, active

    def _deadline(
        self,
        delivery: Any,
        position: Optional[Point],
        destination: Optional[Point],
        now: datetime,
        reasons: List[str],
    ) -> float:
        scheduled_at = getattr(delivery, "scheduled_at", None)
        if scheduled_at is None:
            return 100.0  # sem prazo não penaliza ninguém

        eta_s = 0
        if position is not None and destination is not None:
            eta_s = self._provider.duration_matrix([position, destination])[0][1]
        slack_s = (scheduled_at - now).total_seconds() - eta_s
        if slack_s >= 0:
            reasons.append("Chega dentro do prazo")
            return 100.0

        late_minutes = abs(slack_s) / 60.0
        reasons.append(f"Não chega a tempo (≈{late_minutes:.0f} min de atraso no ETA)")
        return max(0.0, 100.0 - late_minutes * DEADLINE_PENALTY_PER_MINUTE)

    def _fairness(
        self,
        driver_id: str,
        deliveries: Any,
        since: datetime,
        reasons: List[str],
    ) -> float:
        recent = deliveries.count_assigned_since(driver_id, since)
        if recent:
            reasons.append(f"{recent} entrega(s) nas últimas {FAIRNESS_WINDOW_HOURS:.0f}h")
        return max(0.0, 100.0 - recent * FAIRNESS_PENALTY_PER_DELIVERY)

    @staticmethod
    def _resolve_weights() -> Dict[str, float]:
        """Pesos da env, normalizados. Soma zero cai para o default."""
        raw = {
            "proximity": float(settings.dispatch_weight_proximity),
            "load": float(settings.dispatch_weight_load),
            "deadline": float(settings.dispatch_weight_deadline),
            "fairness": float(settings.dispatch_weight_fairness),
        }
        total = sum(max(0.0, value) for value in raw.values())
        if total <= 0:
            logger.warning("dispatch.weights_invalidos — usando os pesos default")
            return dict(DEFAULT_WEIGHTS)
        return {name: max(0.0, value) / total for name, value in raw.items()}
