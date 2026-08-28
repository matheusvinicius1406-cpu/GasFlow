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
from typing import Dict, List, Optional
from datetime import datetime

from app.presentation.dependencies import get_tenant_context, require_admin
from app.domain.security.models import TenantContext

router = APIRouter(prefix="/operations", tags=["operations"])


# ── In-memory store (shared with delivery_ops) ──────────

_in_memory_store = {}


def _get_store():
    return _in_memory_store


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
    store = _get_store()
    drivers = list(store.get("drivers", {}).values())
    result = []

    for d in drivers:
        # Count active deliveries for this driver
        active_deliveries = sum(
            1 for deliv in store.get("deliveries", {}).values()
            if getattr(deliv, 'driver_id', None) == d.id
            and getattr(deliv, 'status', None) and
            hasattr(deliv.status, 'value') and
            deliv.status.value not in ("DELIVERED", "CANCELLED", "FAILED")
        )

        loc = d.location if hasattr(d, 'location') else None
        loc_dict = loc if isinstance(loc, dict) else None

        # Try to get vehicle plate
        vehicle_plate = None
        if hasattr(d, 'vehicle_id') and d.vehicle_id:
            vehicle = store.get("vehicles", {}).get(d.vehicle_id)
            if vehicle:
                vehicle_plate = getattr(vehicle, 'plate', None)

        result.append(DriverLocationResponse(
            driver_id=d.id,
            driver_name=getattr(d, 'name', ''),
            status=d.status.value if hasattr(d.status, 'value') else str(d.status),
            lat=loc_dict.get("lat") if loc_dict else (loc.lat if hasattr(loc, 'lat') else None),
            lng=loc_dict.get("lng") if loc_dict else (loc.lng if hasattr(loc, 'lng') else None),
            last_seen=loc_dict.get("timestamp") if loc_dict else (
                loc.timestamp.isoformat() if hasattr(loc, 'timestamp') else None
            ),
            vehicle_id=getattr(d, 'vehicle_id', None),
            vehicle_plate=vehicle_plate,
            active_deliveries=active_deliveries,
            is_paused=getattr(d, 'status', None) and hasattr(d.status, 'value') and d.status.value == "PAUSED",
            pause_reason=getattr(d, 'pause_reason', None).value if hasattr(getattr(d, 'pause_reason', None), 'value') else None,
        ))

    return result


@router.get("/map/deliveries", response_model=List[ActiveDeliveryResponse])
async def get_active_deliveries(
    ctx: TenantContext = Depends(require_admin),
):
    """Get all active deliveries for the operational map."""
    store = _get_store()
    deliveries = list(store.get("deliveries", {}).values())
    result = []

    for d in deliveries:
        status = d.status.value if hasattr(d.status, 'value') else str(d.status)
        if status in ("DELIVERED", "CANCELLED"):
            continue

        # Get driver name
        driver_name = None
        if d.driver_id:
            driver = store.get("drivers", {}).get(d.driver_id)
            if driver:
                driver_name = getattr(driver, 'name', None)

        addr = d.address
        addr_str = ""
        if hasattr(addr, 'full_address'):
            addr_str = addr.full_address()
        elif hasattr(addr, 'street'):
            addr_str = f"{addr.street}, {addr.number}"

        result.append(ActiveDeliveryResponse(
            delivery_id=d.id,
            order_id=getattr(d, 'order_id', ''),
            customer_name=getattr(d, 'customer_name', ''),
            address=addr_str,
            status=status,
            driver_id=d.driver_id,
            driver_name=driver_name,
            vehicle_id=getattr(d, 'vehicle_id', None),
            scheduled_at=d.scheduled_at.isoformat() if hasattr(d, 'scheduled_at') and d.scheduled_at else None,
            started_at=d.started_at.isoformat() if hasattr(d, 'started_at') and d.started_at else None,
            eta_minutes=d.eta_minutes if hasattr(d, 'eta_minutes') else None,
        ))

    return result


@router.get("/dashboard", response_model=OperationalSummary)
async def get_operational_dashboard(
    ctx: TenantContext = Depends(require_admin),
):
    """Get operational dashboard summary with alerts."""
    store = _get_store()
    drivers = list(store.get("drivers", {}).values())
    deliveries = list(store.get("deliveries", {}).values())
    vehicles = list(store.get("vehicles", {}).values())

    # Driver stats
    drivers_online = sum(1 for d in drivers
                        if hasattr(d.status, 'value') and
                        d.status.value not in ("OFFLINE", "INACTIVE"))
    drivers_available = sum(1 for d in drivers
                           if hasattr(d, 'is_available') and d.is_available)
    drivers_busy = sum(1 for d in drivers
                      if hasattr(d.status, 'value') and d.status.value == "BUSY")
    drivers_paused = sum(1 for d in drivers
                        if hasattr(d.status, 'value') and d.status.value == "PAUSED")
    drivers_offline = sum(1 for d in drivers
                         if hasattr(d.status, 'value') and
                         d.status.value in ("OFFLINE", "INACTIVE"))

    # Delivery stats
    from app.domain.delivery.delivery import DeliveryStatus
    deliveries_pending = sum(1 for d in deliveries
                            if hasattr(d.status, 'value') and d.status.value == "PENDING")
    deliveries_in_progress = sum(1 for d in deliveries
                                if hasattr(d.status, 'value') and
                                d.status.value in ("ASSIGNED", "DISPATCHED", "EN_ROUTE", "ARRIVED"))
    deliveries_completed = sum(1 for d in deliveries
                              if hasattr(d.status, 'value') and d.status.value == "DELIVERED")
    deliveries_failed = sum(1 for d in deliveries
                           if hasattr(d.status, 'value') and d.status.value == "FAILED")

    # Vehicle stats
    vehicles_available = sum(1 for v in vehicles
                            if hasattr(v.status, 'value') and v.status.value == "AVAILABLE")
    vehicles_in_use = sum(1 for v in vehicles
                         if hasattr(v.status, 'value') and v.status.value == "IN_USE")

    # Generate alerts
    alerts = []

    # Alert: pending deliveries without driver
    pending_without_driver = sum(1 for d in deliveries
                                if hasattr(d.status, 'value') and d.status.value == "PENDING"
                                and not getattr(d, 'driver_id', None))
    if pending_without_driver > 0:
        alerts.append(OperationalAlert(
            alert_type="PENDING_NO_DRIVER",
            severity="WARNING",
            message=f"{pending_without_driver} entrega(s) sem motorista atribuído",
            timestamp=datetime.utcnow().isoformat(),
        ))

    # Alert: no available drivers
    if drivers_online > 0 and drivers_available == 0:
        alerts.append(OperationalAlert(
            alert_type="NO_AVAILABLE_DRIVERS",
            severity="CRITICAL",
            message="Nenhum motorista disponível para novas entregas",
            timestamp=datetime.utcnow().isoformat(),
        ))

    # Alert: low vehicle capacity
    from app.domain.delivery.vehicle import VehicleStatus
    low_capacity_vehicles = sum(1 for v in vehicles
                               if hasattr(v, 'has_capacity') and not v.has_capacity
                               and hasattr(v.status, 'value') and v.status.value != "MAINTENANCE")
    if low_capacity_vehicles > 0:
        alerts.append(OperationalAlert(
            alert_type="LOW_VEHICLE_CAPACITY",
            severity="INFO",
            message=f"{low_capacity_vehicles} veículo(s) com capacidade baixa",
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
        vehicles_available=vehicles_available,
        vehicles_in_use=vehicles_in_use,
        alerts=alerts,
    )
