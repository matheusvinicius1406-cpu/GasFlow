"""Plano de rota otimizado (A4) — persistência do resultado do Fase 8.

O `route.optimized` publicado no barramento era efêmero: HTTP response +
evento em memória com ring buffer de 1000. Reiniciava o backend e o
motorista perdia a ordem otimizada. A4 decide persistir o resultado —
tabela própria (`route_plan_records`), **não** `route_records`/`route_stop_records`
que modelam a rota operacional em andamento (status machine PLANNED→…→COMPLETED).

Semântica: upsert — um plano ativo por (tenant_id, driver_id); `plan_version`
incrementa a cada save para auditoria. A tabela só recebe linhas quando
`DELIVERY_SMART_ROUTING_ENABLED=true` (flag default false — Fase 8).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class RoutePlanRecord(Base):
    """Último plano otimizado do entregador (upsert por tenant+driver)."""

    __tablename__ = "route_plan_records"

    __table_args__ = (
        UniqueConstraint("tenant_id", "driver_id", name="uq_route_plan_tenant_driver"),
        Index("ix_route_plan_tenant", "tenant_id"),
        Index("ix_route_plan_driver", "driver_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, default="default", nullable=False)
    driver_id: Mapped[str] = mapped_column(String(36), nullable=False)
    #: Origem do save: ENDPOINT (POST /route/optimize) ou ASSIGN (pós-atribuição).
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="ENDPOINT")
    #: Ordem enviada pelo chamador — permite recalcular `changed` no load.
    input_delivery_ids: Mapped[Optional[list]] = mapped_column(JSON(none_as_null=True), nullable=True)
    ordered_delivery_ids: Mapped[list] = mapped_column(JSON(none_as_null=True), nullable=False)
    total_distance_km: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_duration_s: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    improvement_km: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="haversine")
    #: Polilinha [[lat, lng], ...] — mesmo formato de ibge_model.geom (JSON).
    geometry: Mapped[Optional[list]] = mapped_column(JSON(none_as_null=True), nullable=True)
    #: 1 se ordered != input, 0 caso contrário (snapshot no momento do save).
    changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    origin_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    origin_lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
