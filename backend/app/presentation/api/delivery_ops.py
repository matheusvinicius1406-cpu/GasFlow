"""
Delivery Operations API — FASE 14

Endpoints for deliveries, drivers, vehicles, routes, dispatch.
"""

from fastapi import APIRouter, HTTPException, Depends
from app.presentation.dependencies import get_tenant_context, require_admin, require_role
from app.domain.security.models import TenantContext
from app.infrastructure.stores.shared_store import get_shared_store
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

router = APIRouter(prefix="/delivery", tags=["delivery-ops"])


# ── Schemas ─────────────────────────────────────────────

class AddressSchema(BaseModel):
    street: str = ""
    number: str = ""
    complement: str = ""
    neighborhood: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    reference: str = ""

class CreateDeliveryRequest(BaseModel):
    order_id: str
    customer_codigo: str
    customer_name: str
    address: Optional[AddressSchema] = None
    scheduled_at: Optional[str] = None
    notes: str = ""

class AssignRequest(BaseModel):
    driver_id: str
    vehicle_id: Optional[str] = None

class StatusUpdateRequest(BaseModel):
    status: str
    failure_reason: Optional[str] = None
    failure_notes: str = ""
    proof_type: Optional[str] = None

class CreateRouteRequest(BaseModel):
    driver_id: str
    vehicle_id: Optional[str] = None
    stops: Optional[List[dict]] = None

class CreateDriverRequest(BaseModel):
    name: str
    phone: str
    license_number: Optional[str] = None
    vehicle_id: Optional[str] = None

class CreateVehicleRequest(BaseModel):
    plate: str
    model: str
    capacity: int = 0
    capacity_unit: str = "CYLINDERS"

class LocationUpdateRequest(BaseModel):
    lat: float
    lng: float
    accuracy: Optional[float] = None


# ── Shared store (single source of truth) ───────────────

def _get_store():
    return get_shared_store()


# ── Delivery Endpoints ──────────────────────────────────

@router.post("/deliveries")
async def create_delivery(req: CreateDeliveryRequest, ctx: TenantContext = Depends(require_admin)):
    from app.domain.delivery.delivery import Delivery, AddressSnapshot
    from app.domain.delivery.driver import Driver, DriverStatus
    store = _get_store()
    tenant_id = "default"

    # Check duplicate order
    for d in store.get("deliveries", {}).values():
        if d.order_id == req.order_id and d.tenant_id == tenant_id:
            raise HTTPException(400, "Delivery already exists for this order")

    addr = AddressSnapshot(**(req.address.model_dump() if req.address else {}))
    delivery = Delivery(
        order_id=req.order_id,
        tenant_id=tenant_id,
        customer_codigo=req.customer_codigo,
        customer_name=req.customer_name,
        address=addr,
        notes=req.notes,
    )
    if "deliveries" not in store:
        store["deliveries"] = {}
    store["deliveries"][delivery.id] = delivery
    return {"success": True, "delivery": delivery.to_dict()}


def _d_get(d, key, default=None):
    """Safe accessor for domain entities or dicts."""
    if isinstance(d, dict):
        return d.get(key, default)
    return getattr(d, key, default)


def _d_to_dict(d):
    """Convert domain entity or dict to dict."""
    if isinstance(d, dict):
        return d
    if hasattr(d, 'to_dict'):
        return d.to_dict()
    return d


@router.get("/deliveries")
async def list_deliveries(status: Optional[str] = None, driver_id: Optional[str] = None, ctx: TenantContext = Depends(get_tenant_context)):
    store = _get_store()
    tenant_id = "default"
    deliveries = list(store.get("deliveries", {}).values())
    deliveries = [d for d in deliveries if _d_get(d, 'tenant_id') == tenant_id]
    if status:
        deliveries = [d for d in deliveries if _d_get(d, 'status') == status]
    if driver_id:
        deliveries = [d for d in deliveries if _d_get(d, 'driver_id') == driver_id]
    return {"deliveries": [_d_to_dict(d) for d in deliveries], "count": len(deliveries)}


@router.get("/deliveries/{delivery_id}")
async def get_delivery(delivery_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    store = _get_store()
    delivery = store.get("deliveries", {}).get(delivery_id)
    if not delivery:
        raise HTTPException(404, "Delivery not found")
    return {"delivery": delivery.to_dict()}


@router.patch("/deliveries/{delivery_id}/assign")
async def assign_delivery(delivery_id: str, req: AssignRequest, ctx: TenantContext = Depends(get_tenant_context)):
    from app.domain.delivery.delivery import DeliveryStatus
    from app.domain.delivery.driver import DriverStatus
    store = _get_store()
    tenant_id = "default"
    delivery = store.get("deliveries", {}).get(delivery_id)
    if not delivery:
        raise HTTPException(404, "Delivery not found")
    driver = store.get("drivers", {}).get(req.driver_id)
    if not driver:
        raise HTTPException(404, "Driver not found")
    if not driver.is_available:
        raise HTTPException(400, f"Driver is {driver.status.value}")
    if not delivery.assign(req.driver_id, req.vehicle_id):
        raise HTTPException(400, f"Cannot assign in status {delivery.status.value}")
    driver.set_busy()
    return {"success": True, "delivery": delivery.to_dict()}


@router.patch("/deliveries/{delivery_id}/status")
async def update_delivery_status(delivery_id: str, req: StatusUpdateRequest, ctx: TenantContext = Depends(get_tenant_context)):
    from app.domain.delivery.delivery import DeliveryStatus, DeliveryFailureReason, DeliveryProof, ProofType
    store = _get_store()
    tenant_id = "default"
    delivery = store.get("deliveries", {}).get(delivery_id)
    if not delivery:
        raise HTTPException(404, "Delivery not found")

    if req.status == "EN_ROUTE":
        ok = delivery.start_route()
    elif req.status == "ARRIVED":
        ok = delivery.arrive()
    elif req.status == "DELIVERED":
        proof = None
        if req.proof_type:
            proof = DeliveryProof(delivery_id=delivery_id, proof_type=ProofType(req.proof_type))
        ok = delivery.complete(proof)
    elif req.status == "FAILED":
        reason = DeliveryFailureReason.OTHER
        if req.failure_reason:
            try:
                reason = DeliveryFailureReason(req.failure_reason)
            except ValueError:
                pass
        ok = delivery.fail(reason, req.failure_notes)
    elif req.status == "CANCELLED":
        ok = delivery.cancel()
    else:
        raise HTTPException(400, f"Unknown status: {req.status}")

    if not ok:
        raise HTTPException(400, f"Cannot transition to {req.status}")

    # Release driver on terminal state
    if delivery.status in {DeliveryStatus.DELIVERED, DeliveryStatus.CANCELLED, DeliveryStatus.FAILED}:
        if delivery.driver_id:
            driver = store.get("drivers", {}).get(delivery.driver_id)
            if driver:
                driver.set_available()

    return {"success": True, "delivery": delivery.to_dict()}


# ── Driver Endpoints ────────────────────────────────────

@router.post("/drivers")
async def create_driver(req: CreateDriverRequest, ctx: TenantContext = Depends(require_admin)):
    from app.domain.delivery.driver import Driver
    store = _get_store()
    if "drivers" not in store:
        store["drivers"] = {}
    driver = Driver(
        tenant_id="default",
        name=req.name,
        phone=req.phone,
        license_number=req.license_number,
        vehicle_id=req.vehicle_id,
    )
    store["drivers"][driver.id] = driver
    return {"success": True, "driver": driver.to_dict()}


@router.get("/drivers")
async def list_drivers(status: Optional[str] = None, ctx: TenantContext = Depends(get_tenant_context)):
    store = _get_store()
    drivers = list(store.get("drivers", {}).values())
    drivers = [d for d in drivers if d.tenant_id == "default"]
    if status:
        drivers = [d for d in drivers if d.status.value == status]
    return {"drivers": [d.to_dict() for d in drivers], "count": len(drivers)}


@router.get("/drivers/{driver_id}")
async def get_driver(driver_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    store = _get_store()
    driver = store.get("drivers", {}).get(driver_id)
    if not driver:
        raise HTTPException(404, "Driver not found")
    return {"driver": driver.to_dict()}


@router.patch("/drivers/{driver_id}/location")
async def update_driver_location(driver_id: str, req: LocationUpdateRequest, ctx: TenantContext = Depends(get_tenant_context)):
    store = _get_store()
    driver = store.get("drivers", {}).get(driver_id)
    if not driver:
        raise HTTPException(404, "Driver not found")
    driver.update_location(req.lat, req.lng, req.accuracy)
    return {"success": True}


@router.patch("/drivers/{driver_id}/status")
async def update_driver_status(driver_id: str, status: str, ctx: TenantContext = Depends(get_tenant_context)):
    from app.domain.delivery.driver import DriverStatus
    store = _get_store()
    driver = store.get("drivers", {}).get(driver_id)
    if not driver:
        raise HTTPException(404, "Driver not found")
    try:
        new_status = DriverStatus(status)
    except ValueError:
        raise HTTPException(400, f"Invalid status: {status}")
    if new_status == DriverStatus.AVAILABLE:
        driver.set_available()
    elif new_status == DriverStatus.OFFLINE:
        driver.go_offline()
    elif new_status == DriverStatus.INACTIVE:
        driver.deactivate()
    else:
        driver.status = new_status
    return {"success": True, "driver": driver.to_dict()}


# ── Vehicle Endpoints (Database-backed) ───────────────

def _get_vehicle_repo():
    from app.infrastructure.database.dependencies import get_db
    from app.infrastructure.repositories.vehicle_repository import VehicleRepository
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    db = DBSession(bind=engine)
    return VehicleRepository(db, tenant_id="default"), db


@router.post("/vehicles")
async def create_vehicle(req: CreateVehicleRequest, ctx: TenantContext = Depends(require_admin)):
    repo, db = _get_vehicle_repo()
    try:
        vehicle = repo.create_vehicle(
            plate=req.plate,
            model=req.model,
            vehicle_type="VAN",
            capacity_total=req.capacity,
        )
        return {
            "success": True,
            "vehicle": {
                "id": str(vehicle.id),
                "plate": vehicle.plate,
                "model": vehicle.model,
                "capacity_total": vehicle.capacity_total,
                "status": vehicle.status,
                "tenant_id": vehicle.tenant_id,
                "created_at": vehicle.created_at.isoformat() if vehicle.created_at else None,
            }
        }
    finally:
        db.close()


@router.get("/vehicles")
async def list_vehicles(status: Optional[str] = None, ctx: TenantContext = Depends(get_tenant_context)):
    repo, db = _get_vehicle_repo()
    try:
        vehicles = repo.list_vehicles(status=status)
        return {
            "vehicles": [
                {
                    "id": str(v.id),
                    "plate": v.plate,
                    "model": v.model,
                    "capacity_total": v.capacity_total,
                    "status": v.status,
                    "assigned_driver_id": v.assigned_driver_id,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                }
                for v in vehicles
            ],
            "count": len(vehicles),
        }
    finally:
        db.close()


# ── Route Endpoints ─────────────────────────────────────

@router.post("/routes")
async def create_route(req: CreateRouteRequest, ctx: TenantContext = Depends(require_admin)):
    from app.domain.delivery.route import Route
    store = _get_store()
    if "routes" not in store:
        store["routes"] = {}
    route = Route(
        tenant_id="default",
        driver_id=req.driver_id,
        vehicle_id=req.vehicle_id,
    )
    if req.stops:
        for i, stop_data in enumerate(req.stops):
            delivery_id = stop_data.get("delivery_id", "")
            delivery = store.get("deliveries", {}).get(delivery_id)
            addr = ""
            if delivery:
                addr = delivery.address.full_address()
            route.add_stop(
                delivery_id=delivery_id,
                sequence=stop_data.get("sequence", i + 1),
                customer_name=stop_data.get("customer_name", delivery.customer_name if delivery else ""),
                address_snapshot=addr or stop_data.get("address", ""),
            )
    store["routes"][route.id] = route
    return {"success": True, "route": route.to_dict()}


@router.get("/routes")
async def list_routes(status: Optional[str] = None, ctx: TenantContext = Depends(get_tenant_context)):
    store = _get_store()
    routes = list(store.get("routes", {}).values())
    routes = [r for r in routes if r.tenant_id == "default"]
    if status:
        routes = [r for r in routes if r.status.value == status]
    return {"routes": [r.to_dict() for r in routes], "count": len(routes)}


@router.get("/routes/{route_id}")
async def get_route(route_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    store = _get_store()
    route = store.get("routes", {}).get(route_id)
    if not route:
        raise HTTPException(404, "Route not found")
    return {"route": route.to_dict()}


@router.post("/routes/{route_id}/dispatch")
async def dispatch_route(route_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    store = _get_store()
    route = store.get("routes", {}).get(route_id)
    if not route:
        raise HTTPException(404, "Route not found")
    if not route.dispatch():
        raise HTTPException(400, f"Cannot dispatch route in status {route.status.value}")
    return {"success": True, "route": route.to_dict()}


@router.post("/routes/{route_id}/stops/{stop_id}/arrive")
async def arrive_stop(route_id: str, stop_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    store = _get_store()
    route = store.get("routes", {}).get(route_id)
    if not route:
        raise HTTPException(404, "Route not found")
    for stop in route.stops:
        if stop.id == stop_id:
            if not stop.arrive():
                raise HTTPException(400, "Cannot arrive at this stop")
            if route.status.value == "DISPATCHED":
                route.start()
            return {"success": True}
    raise HTTPException(404, "Stop not found")


@router.post("/routes/{route_id}/stops/{stop_id}/complete")
async def complete_stop(route_id: str, stop_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    store = _get_store()
    route = store.get("routes", {}).get(route_id)
    if not route:
        raise HTTPException(404, "Route not found")
    for stop in route.stops:
        if stop.id == stop_id:
            if not stop.complete():
                raise HTTPException(400, "Cannot complete this stop")
            # Check if all stops completed
            if all(s.is_terminal for s in route.stops):
                route.complete_route()
            return {"success": True}
    raise HTTPException(404, "Stop not found")


@router.post("/routes/{route_id}/stops/{stop_id}/fail")
async def fail_stop(route_id: str, stop_id: str, reason: str = "", ctx: TenantContext = Depends(get_tenant_context)):
    store = _get_store()
    route = store.get("routes", {}).get(route_id)
    if not route:
        raise HTTPException(404, "Route not found")
    for stop in route.stops:
        if stop.id == stop_id:
            if not stop.fail(reason):
                raise HTTPException(400, "Cannot fail this stop")
            return {"success": True}
    raise HTTPException(404, "Stop not found")


# ── Dispatch Dashboard ──────────────────────────────────

@router.get("/dispatch/summary")
async def dispatch_summary(ctx: TenantContext = Depends(get_tenant_context)):
    store = _get_store()
    tenant_id = "default"
    deliveries = [d for d in store.get("deliveries", {}).values() if d.tenant_id == tenant_id]
    drivers = [d for d in store.get("drivers", {}).values() if d.tenant_id == tenant_id]
    statuses = {}
    for d in deliveries:
        s = d.status.value
        statuses[s] = statuses.get(s, 0) + 1
    return {
        "deliveries": {"total": len(deliveries), "by_status": statuses},
        "drivers": {
            "total": len(drivers),
            "available": sum(1 for d in drivers if d.is_available),
        },
    }


# ── Driver Locations ─────────────────────────────────────

@router.get("/locations")
async def list_driver_locations(ctx: TenantContext = Depends(get_tenant_context)):
    """Get all driver GPS locations for the admin drivers map."""
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDriverLocationRepository
    db = DBSession(bind=engine)
    try:
        loc_repo = SQLAlchemyDriverLocationRepository(db)
        locations = loc_repo.get_all_locations(ctx.tenant_id)
        return {"locations": locations}
    finally:
        db.close()
