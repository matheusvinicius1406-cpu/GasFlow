"""Domínio de rastreio (Fase 7): ETA determinístico e limiares de alerta."""

from app.domain.tracking.eta import (
    DEFAULT_SPEED_KMH,
    EtaEstimate,
    HistoryPoint,
    average_speed_kmh,
    estimate_eta,
)

__all__ = [
    "DEFAULT_SPEED_KMH",
    "EtaEstimate",
    "HistoryPoint",
    "average_speed_kmh",
    "estimate_eta",
]
