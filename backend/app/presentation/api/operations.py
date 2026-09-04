"""
Operations API — Admin Operational Dashboard

Endpoints for real-time operational view:
- Driver locations map
- Active deliveries tracking
- Fleet status summary
- Alerts
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from app.presentation.dependencies import require_admin
from app.domain.security.models import TenantContext

router = APIRouter(prefix="/operations", tags=["operations"])




# ── Schemas ──────────────────────────────────────────────

class DriverLocationResponse(BaseModel):
    driver_id: str
    driver_name: str
    status: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    last_seen: Optional[str] = None
    vehicle_id: Optional[str] = None
    vehicle_plate: Optional[str] = None
    active_deliveries: int = 0
    is_paused: bool = False
    pause_reason: Optional[str] = None


class ActiveDeliveryResponse(BaseModel):
    delivery_id: str
    order_id: str
    customer_name: str
    address: str
    status: str
    driver_id: Optional[str] = None
    driver_name: Optional[str] = None
    vehicle_id: Optional[str] = None
    scheduled_at: Optional[str] = None
    started_at: Optional[str] = None
    eta_minutes: Optional[int] = None


class OperationalAlert(BaseModel):
    alert_type: str
    severity: str  # INFO, WARNING, CRITICAL
    message: str
    driver_id: Optional[str] = None
    delivery_id: Optional[str] = None
    timestamp: str


class OperationalSummary(BaseModel):
    drivers_online: int
    drivers_available: int
    drivers_busy: int
    drivers_paused: int
    drivers_offline: int
    deliveries_pending: int
    deliveries_in_progress: int
    deliveries_completed_today: int
    deliveries_failed_today: int
    vehicles_available: int
    vehicles_in_use: int
    alerts: List[OperationalAlert]


# ── Endpoints ────────────────────────────────────────────

@router.get("/map/drivers", response_model=List[DriverLocationResponse])
async def get_driver_locations(
    ctx: TenantContext = Depends(require_admin),
):
    """Get all driver locations for the operational map."""
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository
    from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDriverLocationRepository, SQLAlchemyDeliveryPersistenceRepository

    db = DBSession(bind=engine)
    try:
        drv_repo = SQLAlchemyDeliveryDriverRepository(db, ctx.tenant_id)
        loc_repo = SQLAlchemyDriverLocationRepository(db)
        del_repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx.tenant_id)

        drivers = drv_repo.listar_todos()
        result = []

        for d in drivers:
            active_deliveries = len(del_repo.list_by_driver(d.codigo))
            location = loc_repo.get_location(ctx.tenant_id, d.codigo)

            result.append(DriverLocationResponse(
                driver_id=d.codigo,
                driver_name=d.name or '',
                status=d.status.value,
                lat=location.latitude if location else None,
                lng=location.longitude if location else None,
                last_seen=location.recorded_at.isoformat() if location and location.recorded_at else None,
                vehicle_id=d.vehicle_id,
                vehicle_plate=None,
                active_deliveries=active_deliveries,
                is_paused=d.status.value == "PAUSED",
                pause_reason=None,
            ))

        return result
    finally:
        db.close()


@router.get("/map/deliveries", response_model=List[ActiveDeliveryResponse])
async def get_active_deliveries(
    ctx: TenantContext = Depends(require_admin),
):
    """Get all active deliveries for the operational map."""
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository
    from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository

    db = DBSession(bind=engine)
    try:
        del_repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx.tenant_id)
        drv_repo = SQLAlchemyDeliveryDriverRepository(db, ctx.tenant_id)

        all_deliveries = del_repo.list_deliveries(limit=200)
        result = []

        for d in all_deliveries:
            if d.status in ("DELIVERED", "CANCELLED"):
                continue

            driver_name = None
            if d.driver_id:
                driver = drv_repo.buscar_por_codigo(d.driver_id)
                if driver:
                    driver_name = driver.name

            addr_str = d.address_street or ''
            if d.address_number:
                addr_str += f", {d.address_number}"

            result.append(ActiveDeliveryResponse(
                delivery_id=d.delivery_id,
                order_id=d.order_id or '',
                customer_name=d.customer_name or '',
                address=addr_str,
                status=d.status,
                driver_id=d.driver_id,
                driver_name=driver_name,
                vehicle_id=d.vehicle_id,
                scheduled_at=d.scheduled_at.isoformat() if d.scheduled_at else None,
                started_at=d.started_at.isoformat() if d.started_at else None,
                eta_minutes=None,
            ))

        return result
    finally:
        db.close()


@router.get("/dashboard", response_model=OperationalSummary)
async def get_operational_dashboard(
    ctx: TenantContext = Depends(require_admin),
):
    """Get operational dashboard summary with alerts."""
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository
    from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository

    db = DBSession(bind=engine)
    try:
        del_repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx.tenant_id)
        drv_repo = SQLAlchemyDeliveryDriverRepository(db, ctx.tenant_id)

        drivers = drv_repo.listar_todos()
        status_counts = del_repo.count_by_status()
        drivers_online = sum(1 for d in drivers if d.status.value not in ("OFFLINE", "INACTIVE"))
        drivers_available = sum(1 for d in drivers if d.is_available)
        drivers_busy = sum(1 for d in drivers if d.status.value == "BUSY")
        drivers_paused = sum(1 for d in drivers if d.status.value == "PAUSED")
        drivers_offline = sum(1 for d in drivers if d.status.value in ("OFFLINE", "INACTIVE"))

        # Delivery stats from DB counts
        deliveries_pending = status_counts.get("PENDING", 0)
        deliveries_in_progress = (
            status_counts.get("ASSIGNED", 0) + status_counts.get("DISPATCHED", 0) +
            status_counts.get("EN_ROUTE", 0) + status_counts.get("ARRIVED", 0)
        )
        deliveries_completed = status_counts.get("DELIVERED", 0)
        deliveries_failed = status_counts.get("FAILED", 0)

        # Generate alerts
        alerts = []

        if deliveries_pending > 0 and drivers_available == 0 and drivers_online > 0:
            alerts.append(OperationalAlert(
                alert_type="PENDING_NO_DRIVER",
                severity="WARNING",
                message=f"{deliveries_pending} entrega(s) sem motorista disponivel",
                timestamp=datetime.utcnow().isoformat(),
            ))

        if drivers_online > 0 and drivers_available == 0:
            alerts.append(OperationalAlert(
                alert_type="NO_AVAILABLE_DRIVERS",
                severity="CRITICAL",
                message="Nenhum motorista disponivel para novas entregas",
                timestamp=datetime.utcnow().isoformat(),
            ))

        return OperationalSummary(
            drivers_online=drivers_online,
            drivers_available=drivers_available,
            drivers_busy=drivers_busy,
            drivers_paused=drivers_paused,
            drivers_offline=drivers_offline,
            deliveries_pending=deliveries_pending,
            deliveries_in_progress=deliveries_in_progress,
            deliveries_completed_today=deliveries_completed,
            deliveries_failed_today=deliveries_failed,
            vehicles_available=0,
            vehicles_in_use=0,
            alerts=alerts,
        )
    finally:
        db.close()
