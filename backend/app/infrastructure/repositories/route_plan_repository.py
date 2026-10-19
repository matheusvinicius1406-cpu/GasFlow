"""
Route Plan Repository — SQLAlchemy implementation (A4).

Persiste o último resultado da otimização de rota (Fase 8) por
(tenant_id, driver_id) — upsert. `plan_version` incrementa a cada
save. Leituras sempre filtram por tenant (TenantMixin).
"""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.application.routing.optimizer import OptimizedRoute
from app.infrastructure.repositories.route_plan_model import RoutePlanRecord
from app.infrastructure.repositories.tenant_mixin import TenantMixin


class SQLAlchemyRoutePlanRepository(TenantMixin):
    """Repository for optimized route plans (upsert per tenant+driver)."""

    def __init__(self, db: Session, tenant_id: str = "default"):
        super().__init__(db, tenant_id)

    def save_plan(
        self,
        *,
        driver_id: str,
        plan: OptimizedRoute,
        source: str = "ENDPOINT",
        input_delivery_ids: Optional[List[str]] = None,
        origin: Optional[tuple[float, float]] = None,
    ) -> RoutePlanRecord:
        """Upsert do último plano otimizado do entregador."""
        existing = self._filter_by_tenant(RoutePlanRecord).filter(RoutePlanRecord.driver_id == driver_id).first()
        changed = 1 if input_delivery_ids is not None and plan.ordered_delivery_ids != input_delivery_ids else 0
        if existing:
            record = existing
            record.source = source
            record.input_delivery_ids = input_delivery_ids
            record.ordered_delivery_ids = plan.ordered_delivery_ids
            record.total_distance_km = plan.total_distance_km
            record.total_duration_s = plan.total_duration_s
            record.improvement_km = plan.improvement_km
            record.provider = plan.provider
            record.geometry = [list(p) for p in plan.geometry] if plan.geometry else None
            record.changed = changed
            record.origin_lat = origin[0] if origin else None
            record.origin_lng = origin[1] if origin else None
            record.plan_version = (record.plan_version or 0) + 1
            record.updated_at = datetime.utcnow()
        else:
            record = RoutePlanRecord(
                id=str(uuid.uuid4()),
                tenant_id=self.tenant_id,
                driver_id=driver_id,
                source=source,
                input_delivery_ids=input_delivery_ids,
                ordered_delivery_ids=plan.ordered_delivery_ids,
                total_distance_km=plan.total_distance_km,
                total_duration_s=plan.total_duration_s,
                improvement_km=plan.improvement_km,
                provider=plan.provider,
                geometry=[list(p) for p in plan.geometry] if plan.geometry else None,
                changed=changed,
                origin_lat=origin[0] if origin else None,
                origin_lng=origin[1] if origin else None,
                plan_version=1,
            )
            self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_latest(self, driver_id: str) -> Optional[RoutePlanRecord]:
        return (
            self._filter_by_tenant(RoutePlanRecord)
            .filter(RoutePlanRecord.driver_id == driver_id)
            .order_by(RoutePlanRecord.plan_version.desc())
            .first()
        )

    def list_by_tenant(self, limit: int = 50) -> List[RoutePlanRecord]:
        return self._filter_by_tenant(RoutePlanRecord).order_by(RoutePlanRecord.updated_at.desc()).limit(limit).all()

    def delete_for_driver(self, driver_id: str) -> int:
        deleted = self._filter_by_tenant(RoutePlanRecord).filter(RoutePlanRecord.driver_id == driver_id).delete()
        self.db.commit()
        return deleted
