"""
Delivery Operations API — FASE 14

Endpoints for deliveries, drivers, vehicles, routes, dispatch.
All state is backed by the database — no in-memory stores.
"""

from fastapi import APIRouter, HTTPException, Depends
from app.presentation.dependencies import get_tenant_context, require_admin, require_role
from app.domain.security.models import TenantContext
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

router = APIRouter(prefix="/delivery", tags=["delivery-ops"])


# ── Helper: get a DB session ───────────────────────────

def _get_db():
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    return DBSession(bind=engine)


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


# ── Delivery Endpoints (Database-backed) ────────────────

@router.post("/deliveries")
async def create_delivery(req: CreateDeliveryRequest, ctx: TenantContext = Depends(require_admin)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository

    tenant_id = ctx.tenant_id
    db = DBSession(bind=engine)
    try:
        repo = SQLAlchemyDeliveryPersistenceRepository(db, tenant_id)

        # Check duplicate order via DB
        existing = repo.list_deliveries(driver_id=None, limit=1000)
        for d in existing:
            if d.order_id == req.order_id:
                raise HTTPException(400, "Delivery already exists for this order")

        import uuid as _uuid
        addr = req.address.model_dump() if req.address else {}
        record = repo.create_delivery(
            delivery_id=str(_uuid.uuid4()),
            order_id=req.order_id,
            customer_codigo=req.customer_codigo,
            customer_name=req.customer_name,
            address=addr,
            notes=req.notes,
        )
        return {"success": True, "delivery": record.to_dict()}
    finally:
        db.close()


@router.get("/deliveries")
async def list_deliveries(status: Optional[str] = None, driver_id: Optional[str] = None, ctx: TenantContext = Depends(get_tenant_context)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository

    db = DBSession(bind=engine)
    try:
        repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx.tenant_id)
        deliveries = repo.list_deliveries(status=status, driver_id=driver_id, limit=200)
        return {"deliveries": [d.to_dict() for d in deliveries], "count": len(deliveries)}
    finally:
        db.close()


@router.get("/deliveries/{delivery_id}")
async def get_delivery(delivery_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository

    db = DBSession(bind=engine)
    try:
        repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx.tenant_id)
        delivery = repo.get_delivery(delivery_id)
        if not delivery:
            raise HTTPException(404, "Delivery not found")
        return {"delivery": delivery.to_dict()}
    finally:
        db.close()


@router.patch("/deliveries/{delivery_id}/assign")
async def assign_delivery(delivery_id: str, req: AssignRequest, ctx: TenantContext = Depends(get_tenant_context)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository
    from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository

    db = DBSession(bind=engine)
    try:
        del_repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx.tenant_id)
        drv_repo = SQLAlchemyDeliveryDriverRepository(db, ctx.tenant_id)

        delivery = del_repo.get_delivery(delivery_id)
        if not delivery:
            raise HTTPException(404, "Delivery not found")
        driver = drv_repo.buscar_por_codigo(req.driver_id)
        if not driver:
            raise HTTPException(404, "Driver not found")

        new_record = del_repo.assign_delivery(delivery_id, req.driver_id, req.vehicle_id, delivery.version)
        if not new_record:
            raise HTTPException(400, f"Cannot assign in status {delivery.status}")

        # Set driver busy via domain object
        driver.set_busy()
        drv_repo.db.commit()

        return {"success": True, "delivery": new_record.to_dict()}
    finally:
        db.close()


@router.patch("/deliveries/{delivery_id}/status")
async def update_delivery_status(delivery_id: str, req: StatusUpdateRequest, ctx: TenantContext = Depends(get_tenant_context)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository
    from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository

    db = DBSession(bind=engine)
    try:
        del_repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx.tenant_id)
        delivery = del_repo.get_delivery(delivery_id)
        if not delivery:
            raise HTTPException(404, "Delivery not found")

        if req.status == "EN_ROUTE":
            result = del_repo.start_delivery(delivery_id, delivery.version, delivery.driver_id or "")
        elif req.status == "ARRIVED":
            result = del_repo.arrive_delivery(delivery_id, delivery.version)
        elif req.status == "DELIVERED":
            result = del_repo.complete_delivery(
                delivery_id, delivery.version,
                proof_type=req.proof_type,
            )
        elif req.status == "FAILED":
            result = del_repo.fail_delivery(
                delivery_id, delivery.version,
                reason=req.failure_reason or "OTHER",
                notes=req.failure_notes,
            )
        elif req.status == "CANCELLED":
            result = del_repo.cancel_delivery(delivery_id, delivery.version)
        else:
            raise HTTPException(400, f"Unknown status: {req.status}")

        if not result:
            raise HTTPException(400, f"Cannot transition to {req.status}")

        # Release driver on terminal state
        terminal_states = {"DELIVERED", "CANCELLED", "FAILED"}
        if req.status in terminal_states and delivery.driver_id:
            drv_repo = SQLAlchemyDeliveryDriverRepository(db, ctx.tenant_id)
            driver = drv_repo.buscar_por_codigo(delivery.driver_id)
            if driver:
                driver.set_available()
                drv_repo.db.commit()

        return {"success": True, "delivery": result.to_dict()}
    finally:
        db.close()


# ── Driver Endpoints (Database-backed) ─────────────────

@router.post("/drivers")
async def create_driver(req: CreateDriverRequest, ctx: TenantContext = Depends(require_admin)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository
    from app.domain.delivery.driver import Driver as DriverDomain

    db = DBSession(bind=engine)
    try:
        repo = SQLAlchemyDeliveryDriverRepository(db, tenant_id=ctx.tenant_id)
        driver = DriverDomain(
            tenant_id=ctx.tenant_id,
            name=req.name,
            phone=req.phone,
            license_number=req.license_number,
            vehicle_id=req.vehicle_id,
        )
        repo.criar(driver)
        return {"success": True, "driver": driver.to_dict()}
    finally:
        db.close()


@router.get("/drivers")
async def list_drivers(status: Optional[str] = None, ctx: TenantContext = Depends(get_tenant_context)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository

    db = DBSession(bind=engine)
    try:
        repo = SQLAlchemyDeliveryDriverRepository(db, tenant_id=ctx.tenant_id)
        drivers = repo.listar_todos()
        if status:
            drivers = [d for d in drivers if d.status.value == status]
        return {"drivers": [d.to_dict() for d in drivers], "count": len(drivers)}
    finally:
        db.close()


@router.get("/drivers/{driver_id}")
async def get_driver(driver_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository

    db = DBSession(bind=engine)
    try:
        repo = SQLAlchemyDeliveryDriverRepository(db, tenant_id=ctx.tenant_id)
        driver = repo.buscar_por_codigo(driver_id)
        if not driver:
            raise HTTPException(404, "Driver not found")
        return {"driver": driver.to_dict()}
    finally:
        db.close()


@router.patch("/drivers/{driver_id}/location")
async def update_driver_location(driver_id: str, req: LocationUpdateRequest, ctx: TenantContext = Depends(get_tenant_context)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository
    from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDriverLocationRepository

    db = DBSession(bind=engine)
    try:
        drv_repo = SQLAlchemyDeliveryDriverRepository(db, tenant_id=ctx.tenant_id)
        driver = drv_repo.buscar_por_codigo(driver_id)
        if not driver:
            raise HTTPException(404, "Driver not found")

        # Update domain object
        driver.update_location(req.lat, req.lng, req.accuracy)
        drv_repo.db.commit()

        # Persist to GPS table
        loc_repo = SQLAlchemyDriverLocationRepository(db)
        loc_repo.upsert_location(
            tenant_id=ctx.tenant_id,
            driver_id=driver_id,
            latitude=req.lat,
            longitude=req.lng,
            accuracy=req.accuracy,
        )
        db.commit()
        return {"success": True}
    finally:
        db.close()


@router.patch("/drivers/{driver_id}/status")
async def update_driver_status(driver_id: str, status: str, ctx: TenantContext = Depends(get_tenant_context)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository
    from app.domain.delivery.driver import DriverStatus

    db = DBSession(bind=engine)
    try:
        repo = SQLAlchemyDeliveryDriverRepository(db, tenant_id=ctx.tenant_id)
        driver = repo.buscar_por_codigo(driver_id)
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
        repo.db.commit()
        return {"success": True, "driver": driver.to_dict()}
    finally:
        db.close()


# ── Vehicle Endpoints (Database-backed) ───────────────

def _get_vehicle_repo():
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.vehicle_repository import VehicleRepository
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
                "id": str(vehicle.id), "plate": vehicle.plate,
                "model": vehicle.model, "capacity_total": vehicle.capacity_total,
                "status": vehicle.status, "tenant_id": vehicle.tenant_id,
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
                    "id": str(v.id), "plate": v.plate, "model": v.model,
                    "capacity_total": v.capacity_total, "status": v.status,
                    "assigned_driver_id": v.assigned_driver_id,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                }
                for v in vehicles
            ],
            "count": len(vehicles),
        }
    finally:
        db.close()


# ── Route Endpoints (Database-backed) ──────────────────

@router.post("/routes")
async def create_route(req: CreateRouteRequest, ctx: TenantContext = Depends(require_admin)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.route_repository import SQLAlchemyRouteRepository

    db = DBSession(bind=engine)
    try:
        repo = SQLAlchemyRouteRepository(db)
        route = repo.create(
            tenant_id=ctx.tenant_id,
            driver_id=req.driver_id,
            vehicle_id=req.vehicle_id,
            status="PLANNED",
        )
        if req.stops:
            for i, stop_data in enumerate(req.stops):
                repo.add_stop(
                    route_id=route.id,
                    delivery_id=stop_data.get("delivery_id", ""),
                    sequence=stop_data.get("sequence", i + 1),
                    customer_name=stop_data.get("customer_name", ""),
                    address_snapshot=stop_data.get("address", ""),
                )
        stops = repo.get_stops(route.id)
        return {"success": True, "route": {
            "id": route.id, "tenant_id": route.tenant_id,
            "driver_id": route.driver_id, "vehicle_id": route.vehicle_id,
            "status": route.status, "stops": [
                {"id": s.id, "delivery_id": s.delivery_id, "sequence": s.sequence,
                 "status": s.status, "customer_name": s.customer_name,
                 "address_snapshot": s.address_snapshot}
                for s in stops
            ],
        }}
    finally:
        db.close()


@router.get("/routes")
async def list_routes(status: Optional[str] = None, ctx: TenantContext = Depends(get_tenant_context)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.route_repository import SQLAlchemyRouteRepository

    db = DBSession(bind=engine)
    try:
        repo = SQLAlchemyRouteRepository(db)
        routes = repo.list_by_tenant(ctx.tenant_id, status=status)
        result = []
        for r in routes:
            stops = repo.get_stops(r.id)
            result.append({
                "id": r.id, "tenant_id": r.tenant_id,
                "driver_id": r.driver_id, "vehicle_id": r.vehicle_id,
                "status": r.status, "stops": [
                    {"id": s.id, "delivery_id": s.delivery_id, "sequence": s.sequence,
                     "status": s.status, "customer_name": s.customer_name}
                    for s in stops
                ],
            })
        return {"routes": result, "count": len(result)}
    finally:
        db.close()


@router.get("/routes/{route_id}")
async def get_route(route_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.route_repository import SQLAlchemyRouteRepository

    db = DBSession(bind=engine)
    try:
        repo = SQLAlchemyRouteRepository(db)
        route = repo.get_by_id(route_id)
        if not route or route.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Route not found")
        stops = repo.get_stops(route.id)
        return {"route": {
            "id": route.id, "tenant_id": route.tenant_id,
            "driver_id": route.driver_id, "vehicle_id": route.vehicle_id,
            "status": route.status, "stops": [
                {"id": s.id, "delivery_id": s.delivery_id, "sequence": s.sequence,
                 "status": s.status, "customer_name": s.customer_name,
                 "address_snapshot": s.address_snapshot}
                for s in stops
            ],
        }}
    finally:
        db.close()


@router.post("/routes/{route_id}/dispatch")
async def dispatch_route(route_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.route_repository import SQLAlchemyRouteRepository

    db = DBSession(bind=engine)
    try:
        repo = SQLAlchemyRouteRepository(db)
        route = repo.get_by_id(route_id)
        if not route or route.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Route not found")
        if route.status != "PLANNED":
            raise HTTPException(400, f"Cannot dispatch route in status {route.status}")
        repo.update(route_id, status="DISPATCHED")
        return {"success": True, "route": {"id": route_id, "status": "DISPATCHED"}}
    finally:
        db.close()


@router.post("/routes/{route_id}/stops/{stop_id}/arrive")
async def arrive_stop(route_id: str, stop_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.route_repository import SQLAlchemyRouteRepository

    db = DBSession(bind=engine)
    try:
        repo = SQLAlchemyRouteRepository(db)
        route = repo.get_by_id(route_id)
        if not route or route.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Route not found")
        stops = repo.get_stops(route_id)
        stop = next((s for s in stops if s.id == stop_id), None)
        if not stop:
            raise HTTPException(404, "Stop not found")
        if stop.status not in ("PENDING", "IN_PROGRESS"):
            raise HTTPException(400, "Cannot arrive at this stop")
        repo.update_stop(stop_id, status="IN_PROGRESS")
        if route.status == "DISPATCHED":
            repo.update(route_id, status="IN_PROGRESS")
        return {"success": True}
    finally:
        db.close()


@router.post("/routes/{route_id}/stops/{stop_id}/complete")
async def complete_stop(route_id: str, stop_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.route_repository import SQLAlchemyRouteRepository

    db = DBSession(bind=engine)
    try:
        repo = SQLAlchemyRouteRepository(db)
        route = repo.get_by_id(route_id)
        if not route or route.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Route not found")
        stops = repo.get_stops(route_id)
        stop = next((s for s in stops if s.id == stop_id), None)
        if not stop:
            raise HTTPException(404, "Stop not found")
        if stop.status in ("COMPLETED", "FAILED", "SKIPPED"):
            raise HTTPException(400, "Cannot complete this stop")
        repo.update_stop(stop_id, status="COMPLETED")
        # Check if all stops completed
        all_stops = repo.get_stops(route_id)
        all_terminal = all(s.status in ("COMPLETED", "FAILED", "SKIPPED") for s in all_stops)
        if all_terminal:
            repo.update(route_id, status="COMPLETED")
        return {"success": True}
    finally:
        db.close()


@router.post("/routes/{route_id}/stops/{stop_id}/fail")
async def fail_stop(route_id: str, stop_id: str, reason: str = "", ctx: TenantContext = Depends(get_tenant_context)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.route_repository import SQLAlchemyRouteRepository

    db = DBSession(bind=engine)
    try:
        repo = SQLAlchemyRouteRepository(db)
        route = repo.get_by_id(route_id)
        if not route or route.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Route not found")
        stops = repo.get_stops(route_id)
        stop = next((s for s in stops if s.id == stop_id), None)
        if not stop:
            raise HTTPException(404, "Stop not found")
        if stop.status in ("COMPLETED", "FAILED", "SKIPPED"):
            raise HTTPException(400, "Cannot fail this stop")
        repo.update_stop(stop_id, status="FAILED", notes=reason)
        return {"success": True}
    finally:
        db.close()


# ── Dispatch Dashboard (Database-backed) ───────────────

@router.get("/dispatch/summary")
async def dispatch_summary(ctx: TenantContext = Depends(get_tenant_context)):
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository

    db = DBSession(bind=engine)
    try:
        del_repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx.tenant_id)
        status_counts = del_repo.count_by_status()
        total = sum(status_counts.values())
        return {
            "deliveries": {"total": total, "by_status": status_counts},
            "drivers": {
                "total": 0,  # Will be enriched when driver count query is added
                "available": 0,
            },
        }
    finally:
        db.close()


# ── Driver Locations (Database-backed) ─────────────────

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


# ── Backward-compat helper for printer/reports ─────────

def get_store():
    """Backward-compatible accessor — returns an empty dict.
    All real state is now in the database. This exists solely so
    that printer.py and reports.py don't crash on import."""
    return {}
