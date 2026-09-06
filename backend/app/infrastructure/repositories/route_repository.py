"""
Route Persistence Repository — SQLAlchemy implementation.

Replaces in-memory shared_store["routes"] with database persistence.
"""

from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.infrastructure.repositories.route_model import RouteRecord, RouteStopRecord


class SQLAlchemyRouteRepository:
    """Repository for delivery routes — replaces in-memory store["routes"]."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, route_id: str) -> Optional[RouteRecord]:
        return self.db.query(RouteRecord).filter(RouteRecord.id == route_id).first()

    def list_by_tenant(self, tenant_id: str, status: str = None, driver_id: str = None) -> List[RouteRecord]:
        q = self.db.query(RouteRecord).filter(RouteRecord.tenant_id == tenant_id)
        if status:
            q = q.filter(RouteRecord.status == status)
        if driver_id:
            q = q.filter(RouteRecord.driver_id == driver_id)
        return q.order_by(RouteRecord.created_at.desc()).all()

    def create(self, **kwargs) -> RouteRecord:
        import uuid as _uuid

        if "id" not in kwargs or not kwargs["id"]:
            kwargs["id"] = str(_uuid.uuid4())
        model = RouteRecord(**kwargs)
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def update(self, route_id: str, **kwargs) -> Optional[RouteRecord]:
        model = self.get_by_id(route_id)
        if not model:
            return None
        for key, value in kwargs.items():
            if hasattr(model, key):
                setattr(model, key, value)
        model.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(model)
        return model

    # ── Stops ──────────────────────────────────────────

    def add_stop(
        self,
        route_id: str,
        delivery_id: str,
        sequence: int,
        status: str = "PENDING",
        customer_name: str = "",
        customer_phone: str = "",
        address_snapshot: str = "",
    ) -> RouteStopRecord:
        import uuid as _uuid

        stop = RouteStopRecord(
            id=str(_uuid.uuid4()),
            route_id=route_id,
            delivery_id=delivery_id,
            sequence=sequence,
            status=status,
            customer_name=customer_name,
            customer_phone=customer_phone,
            address_snapshot=address_snapshot,
        )
        self.db.add(stop)
        self.db.commit()
        self.db.refresh(stop)
        return stop

    def get_stops(self, route_id: str) -> List[RouteStopRecord]:
        return (
            self.db.query(RouteStopRecord)
            .filter(RouteStopRecord.route_id == route_id)
            .order_by(RouteStopRecord.sequence)
            .all()
        )

    def update_stop(self, stop_id: str, **kwargs) -> Optional[RouteStopRecord]:
        model = self.db.query(RouteStopRecord).filter(RouteStopRecord.id == stop_id).first()
        if not model:
            return None
        for key, value in kwargs.items():
            if hasattr(model, key):
                setattr(model, key, value)
        self.db.commit()
        self.db.refresh(model)
        return model

    def delete_stops(self, route_id: str):
        self.db.query(RouteStopRecord).filter(RouteStopRecord.route_id == route_id).delete()
        self.db.commit()
