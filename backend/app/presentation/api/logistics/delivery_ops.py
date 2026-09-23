"""
Delivery Operations API — FASE 14

Endpoints for deliveries, drivers, vehicles, routes, dispatch.
All state is backed by the database — no in-memory stores.
"""

from fastapi import APIRouter, HTTPException, Depends
from app.presentation.dependencies import get_tenant_context, require_admin
from app.domain.security.models import TenantContext
from app.presentation.schemas.delivery import CreateDriverResponse
from pydantic import BaseModel
from typing import Optional, List

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
async def list_deliveries(
    status: Optional[str] = None, driver_id: Optional[str] = None, ctx: TenantContext = Depends(get_tenant_context)
):
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

        # O status do entregador vive no model — a entidade devolvida por
        # `buscar_por_codigo` é um dataclass desconectado e não tem `set_busy()`.
        # Chamar o método antigo estourava AttributeError: a atribuição era
        # persistida e a resposta virava 500, derrubando também a otimização de
        # rota logo abaixo.
        drv_repo.set_status(req.driver_id, "BUSY")

        # Fase 8 (decisão 10–12): otimização best-effort. Não atrasa nem
        # derruba a confirmação da atribuição — qualquer exceção é engolida
        # e logada em debug. O padrão segue `_evaluate_alerts` no
        # `driver_location_service.py`.
        _try_optimize_after_assign(ctx.tenant_id, req.driver_id)

        return {"success": True, "delivery": new_record.to_dict()}
    finally:
        db.close()


@router.patch("/deliveries/{delivery_id}/status")
async def update_delivery_status(
    delivery_id: str, req: StatusUpdateRequest, ctx: TenantContext = Depends(get_tenant_context)
):
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
                delivery_id,
                delivery.version,
                proof_type=req.proof_type,
            )
        elif req.status == "FAILED":
            result = del_repo.fail_delivery(
                delivery_id,
                delivery.version,
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
            # Libera o entregador (mesmo motivo do assign: escrita no model).
            drv_repo.set_status(delivery.driver_id, "AVAILABLE")

        return {"success": True, "delivery": result.to_dict()}
    finally:
        db.close()


# ── Driver Endpoints (Database-backed) ─────────────────


@router.post("/drivers", status_code=201, response_model=CreateDriverResponse)
async def create_driver(req: CreateDriverRequest, ctx: TenantContext = Depends(require_admin)):
    """Alias de `POST /admin/drivers`: cadastra entregador **com** credencial.

    Mesmo efeito e mesmo contrato do canônico — entidade + `User(role=DRIVER)` +
    membership na mesma transação, devolvendo a senha temporária. Antes esta
    rota criava só a entidade, e o entregador cadastrado por aqui **não tinha
    como abrir o app** (o login é `/auth/login`).

    `license_number` é gravado em `document` (CPF/CNH): o nome é o do request
    histórico, a coluna é a do model. Nenhum campo do request é descartado.
    """
    from sqlalchemy.orm import Session as DBSession
    from app.application.delivery.use_cases import (
        CreateDriverWithCredentialUseCase,
        DriverRoleMissingError,
        DriverUsernameTakenError,
    )
    from app.infrastructure.database.init_db import engine

    db = DBSession(bind=engine)
    try:
        try:
            result = CreateDriverWithCredentialUseCase(db, ctx.tenant_id, actor_id=ctx.user_id or "").execute(
                nome=req.name,
                telefone=req.phone,
                document=req.license_number,
                vehicle_id=req.vehicle_id,
            )
        except DriverRoleMissingError as exc:
            raise HTTPException(400, "Role DRIVER not found") from exc
        except DriverUsernameTakenError as exc:
            raise HTTPException(400, "Username already exists") from exc
    finally:
        db.close()

    return CreateDriverResponse(
        driver_id=result["driver_id"],
        username=result["username"],
        temporary_password=result["temporary_password"],
    )


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
        snapshot = repo.snapshot(driver_id)
        if not snapshot:
            raise HTTPException(404, "Driver not found")
        return {"driver": snapshot}
    finally:
        db.close()


@router.patch("/drivers/{driver_id}/location")
async def update_driver_location(
    driver_id: str, req: LocationUpdateRequest, ctx: TenantContext = Depends(get_tenant_context)
):
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
        if not repo.snapshot(driver_id):
            raise HTTPException(404, "Driver not found")
        try:
            new_status = DriverStatus(status)
        except ValueError as exc:
            raise HTTPException(400, f"Invalid status: {status}") from exc
        # Persiste pelo model — mutar a entidade desconectada não chegava ao banco.
        repo.set_status(driver_id, new_status.value)
        return {"success": True, "driver": repo.snapshot(driver_id)}
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
                "id": str(vehicle.id),
                "plate": vehicle.plate,
                "model": vehicle.model,
                "capacity_total": vehicle.capacity_total,
                "status": vehicle.status,
                "tenant_id": vehicle.tenant_id,
                "created_at": vehicle.created_at.isoformat() if vehicle.created_at else None,
            },
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
        return {
            "success": True,
            "route": {
                "id": route.id,
                "tenant_id": route.tenant_id,
                "driver_id": route.driver_id,
                "vehicle_id": route.vehicle_id,
                "status": route.status,
                "stops": [
                    {
                        "id": s.id,
                        "delivery_id": s.delivery_id,
                        "sequence": s.sequence,
                        "status": s.status,
                        "customer_name": s.customer_name,
                        "address_snapshot": s.address_snapshot,
                    }
                    for s in stops
                ],
            },
        }
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
            result.append(
                {
                    "id": r.id,
                    "tenant_id": r.tenant_id,
                    "driver_id": r.driver_id,
                    "vehicle_id": r.vehicle_id,
                    "status": r.status,
                    "stops": [
                        {
                            "id": s.id,
                            "delivery_id": s.delivery_id,
                            "sequence": s.sequence,
                            "status": s.status,
                            "customer_name": s.customer_name,
                        }
                        for s in stops
                    ],
                }
            )
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
        return {
            "route": {
                "id": route.id,
                "tenant_id": route.tenant_id,
                "driver_id": route.driver_id,
                "vehicle_id": route.vehicle_id,
                "status": route.status,
                "stops": [
                    {
                        "id": s.id,
                        "delivery_id": s.delivery_id,
                        "sequence": s.sequence,
                        "status": s.status,
                        "customer_name": s.customer_name,
                        "address_snapshot": s.address_snapshot,
                    }
                    for s in stops
                ],
            }
        }
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


# ── Driver Stock (F7 — estoque carregado pelo entregador) ──


class DriverStockLoadRequest(BaseModel):
    driver_id: str
    product_codigo: str
    quantity: int


class DriverStockDamageRequest(BaseModel):
    driver_id: str
    product_codigo: str
    quantity: int
    reason: str


class DriverStockReconcileRequest(BaseModel):
    driver_id: str
    counts: dict  # {product_codigo: cheios informados}
    empty_returned: dict = {}  # {product_codigo: vazios devolvidos à base}


class DriverSuggestRequest(BaseModel):
    delivery_id: str


class RouteOptimizeRequest(BaseModel):
    """Fase 8: reordenar as entregas de um entregador."""

    driver_id: str
    delivery_ids: List[str] = []


@router.get("/drivers/{driver_id}/stock")
async def get_driver_stock(driver_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    """Saldos do estoque carregado pelo entregador, por produto."""
    from app.application.delivery.driver_stock_service import DriverStockService

    db = _get_db()
    try:
        svc = DriverStockService(db, ctx.tenant_id)
        return {"driver_id": driver_id, "stock": svc.get_stock(driver_id)}
    finally:
        db.close()


@router.post("/drivers/{driver_id}/stock/load")
async def load_driver_stock(
    driver_id: str, req: DriverStockLoadRequest, ctx: TenantContext = Depends(get_tenant_context)
):
    """Carga: operador confirma N cheios carregados pelo entregador (C1).

    Empréstimo temporário — NÃO debita a base. Bloqueada quando o
    entregador tem divergência pendente (blocked).
    """
    from app.application.delivery.driver_stock_service import DriverStockService, DriverStockError

    db = _get_db()
    try:
        svc = DriverStockService(db, ctx.tenant_id)
        return svc.load_tanks(driver_id, req.product_codigo, req.quantity, actor_id=ctx.user_id)
    except DriverStockError as e:
        raise HTTPException(e.status_code, e.message) from e
    finally:
        db.close()


@router.post("/drivers/{driver_id}/stock/damage")
async def damage_driver_stock(
    driver_id: str, req: DriverStockDamageRequest, ctx: TenantContext = Depends(get_tenant_context)
):
    """Avaria: motivo obrigatório; debita o entregador E a base (audit)."""
    from app.application.delivery.driver_stock_service import DriverStockService, DriverStockError

    db = _get_db()
    try:
        svc = DriverStockService(db, ctx.tenant_id)
        return svc.register_damage(driver_id, req.product_codigo, req.quantity, req.reason, actor_id=ctx.user_id)
    except DriverStockError as e:
        raise HTTPException(e.status_code, e.message) from e
    finally:
        db.close()


@router.post("/drivers/{driver_id}/stock/reconcile")
async def reconcile_driver_stock(
    driver_id: str, req: DriverStockReconcileRequest, ctx: TenantContext = Depends(get_tenant_context)
):
    """Fim de turno: carga − entregas − avarias = cheios + vazios.

    Divergência > tolerância (driver.stock.tolerance) → alerta + bloqueio
    de novas cargas até reconciliação manual.
    """
    from app.application.delivery.driver_stock_service import DriverStockService

    db = _get_db()
    try:
        svc = DriverStockService(db, ctx.tenant_id)
        return svc.reconcile(driver_id, req.counts, req.empty_returned, actor_id=ctx.user_id)
    finally:
        db.close()


@router.post("/drivers/{driver_id}/stock/unblock")
async def unblock_driver_stock(driver_id: str, ctx: TenantContext = Depends(require_admin)):
    """Desbloqueia cargas após reconciliação manual (admin-only)."""
    from app.application.delivery.driver_stock_service import DriverStockService

    db = _get_db()
    try:
        svc = DriverStockService(db, ctx.tenant_id)
        return svc.unblock(driver_id, actor_id=ctx.user_id)
    finally:
        db.close()


@router.post("/dispatch/suggest")
async def suggest_driver_for_delivery(req: DriverSuggestRequest, ctx: TenantContext = Depends(get_tenant_context)):
    """Sugestão inteligente de entregador para a entrega (F7, C3).

    Elegibilidade = cheios disponíveis no driver_stock + disponível;
    score = proximidade (posição GPS recente) + folga de capacidade.
    Retorna ranking + explicação — o OPERADOR confirma (assign atual).
    """
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_persistence_repository import (
        SQLAlchemyDeliveryPersistenceRepository,
        SQLAlchemyDeliveryDriverRepository,
    )
    from app.application.delivery.driver_stock_service import DriverStockService
    from app.domain.delivery.dispatch_engine import DispatchEngine, DispatchMode, OrderRequest, DriverCandidate

    db = DBSession(bind=engine)
    try:
        del_repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx.tenant_id)
        drv_repo = SQLAlchemyDeliveryDriverRepository(db, ctx.tenant_id)
        delivery = del_repo.get_delivery(req.delivery_id)
        if not delivery:
            raise HTTPException(404, "Delivery not found")
        if delivery.driver_id is not None and delivery.status != "PENDING":
            pass  # sugestão permitida para reatribuição também

        # Itens do pedido → demandas por produto
        from app.infrastructure.repositories.order_item_model import OrderItemModel

        items = db.query(OrderItemModel).filter(OrderItemModel.order_codigo == delivery.order_id).all()
        demand: dict = {}
        for it in items:
            demand[it.product_codigo] = demand.get(it.product_codigo, 0) + it.quantity

        stock_svc = DriverStockService(db, ctx.tenant_id)
        drivers = drv_repo.listar_todos()
        candidates: list = []
        for d in drivers:
            if not d.ativo:
                continue
            model = drv_repo.find_by_id_as_model(d.codigo)
            capacity = stock_svc.eligible_capacity(d.codigo)
            candidates.append(
                DriverCandidate(
                    driver_id=d.codigo,
                    driver_name=d.nome,
                    vehicle_id=model.vehicle_id if model else None,
                    status=model.status if model else "AVAILABLE",
                    is_active=bool(d.ativo),
                    capacity=capacity,
                )
            )

        # Posição GPS mais recente por entregador (mapa do operador)
        from app.infrastructure.repositories.delivery_persistence_model import DriverLocationRecord

        locs = (
            db.query(DriverLocationRecord)
            .filter(DriverLocationRecord.tenant_id == ctx.tenant_id)
            .order_by(DriverLocationRecord.timestamp.desc())
            .limit(200)
            .all()
        )
        seen = set()
        loc_by_driver = {}
        for loc in locs:
            if loc.driver_id in seen:
                continue
            seen.add(loc.driver_id)
            loc_by_driver[loc.driver_id] = loc
        for c in candidates:
            loc = loc_by_driver.get(c.driver_id)
            if loc:
                c.latitude, c.longitude = loc.latitude, loc.longitude

        order = OrderRequest(
            order_id=delivery.order_id,
            tenant_id=ctx.tenant_id,
            customer_codigo=delivery.customer_codigo,
            customer_name=delivery.customer_name,
            latitude=delivery.address_lat,
            longitude=delivery.address_lng,
        )
        order.items = [
            type("OrderItem", (), {"product_codigo": pc, "product_name": pc, "quantity": qty})()
            for pc, qty in demand.items()
        ]

        # Fase 9: com a flag ligada, o ranking passa pelo DispatchScorer (posição
        # do histórico, prazo e fairness), mas o GATE de elegibilidade continua o
        # mesmo — `filter_candidate` segue decidindo quem pode receber a entrega.
        # Score não é elegibilidade: capacidade física não se negocia por ponto.
        from app.core.config import settings

        if settings.delivery_smart_dispatch_enabled:
            from app.application.dispatch.scorer import DispatchScorer
            from app.domain.delivery.dispatch_engine import filter_candidate

            verdicts = [(c, filter_candidate(c, order)) for c in candidates]
            eligible = [c.driver_id for c, verdict in verdicts if verdict.valid]
            scored = DispatchScorer(db, ctx.tenant_id).score(delivery_id=req.delivery_id, candidate_driver_ids=eligible)

            by_id = {c.driver_id: c for c in candidates}
            recommendations = []
            for scored_driver in scored[:3]:
                candidate = by_id.get(scored_driver.driver_id)
                capacity_fit: dict = {}
                if candidate is not None:
                    for item in order.items:
                        available = candidate.capacity.get(item.product_codigo, 0)
                        capacity_fit[item.product_codigo] = {
                            "product": item.product_name,
                            "needed": item.quantity,
                            "available": available,
                            "fits": available >= item.quantity,
                        }
                recommendations.append(
                    {
                        "driver_id": scored_driver.driver_id,
                        "driver_name": scored_driver.driver_name,
                        "vehicle_id": candidate.vehicle_id if candidate else None,
                        "vehicle_plate": candidate.vehicle_plate if candidate else None,
                        "score": scored_driver.total,
                        "distance_km": scored_driver.distance_km,
                        "capacity_fit": capacity_fit,
                        "explanation": scored_driver.reasons,
                    }
                )

            # Fase 9: publica dispatch.scored para auditoria (só quando o scorer
            # decidiu — flag ligada, fluxo real). Não é publicado pelo preview
            # read-only (decisão 6).
            if scored:
                from app.domain.events.event_bus import EventType, publish_delivery_event

                publish_delivery_event(
                    EventType.DISPATCH_SCORED,
                    req.delivery_id,
                    ctx.tenant_id,
                    data={
                        "delivery_id": req.delivery_id,
                        "candidates": [
                            {
                                "driver_id": s.driver_id,
                                "total": s.total,
                                "breakdown": s.breakdown,
                            }
                            for s in scored
                        ],
                    },
                )

            return {
                "success": True,
                "order_id": delivery.order_id,
                "total_candidates": len(candidates),
                "eligible": len(scored),
                "rejected_count": len(candidates) - len(scored),
                "rejected": [
                    {
                        "driver_id": c.driver_id,
                        "driver_name": c.driver_name,
                        "reason": verdict.reason.value if verdict.reason else "UNKNOWN",
                        "details": verdict.details,
                    }
                    for c, verdict in verdicts
                    if not verdict.valid
                ],
                "recommendations": recommendations,
                "source": "dispatch-scorer",
            }

        engine = DispatchEngine(mode=DispatchMode.ASSISTED)
        return engine.recommend(order, candidates)
    finally:
        db.close()


# ── ETA até o endereço da entrega (Fase 7.1) ───────────


@router.get("/deliveries/{delivery_id}/eta")
async def delivery_eta(
    delivery_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """ETA do entregador atribuído até o endereço da entrega.

    - 404 quando a entrega não existe (no tenant) ou não tem entregador;
    - 404 quando o entregador ainda não tem posição conhecida;
    - 422 quando o endereço não tem coordenadas — é a verdade: sem lat/lng não
      há como estimar, e inventar coordenada seria pior que o erro.
    """
    from app.application.tracking.eta_service import DriverEtaService
    from app.infrastructure.repositories.delivery_persistence_repository import (
        SQLAlchemyDeliveryPersistenceRepository,
    )

    db = _get_db()
    try:
        record = SQLAlchemyDeliveryPersistenceRepository(db, tenant_id=ctx.tenant_id).get_delivery(delivery_id)
        if not record:
            raise HTTPException(status_code=404, detail="Entrega não encontrada")
        if not record.driver_id:
            raise HTTPException(status_code=404, detail="Entrega sem entregador atribuído")
        if record.address_lat is None or record.address_lng is None:
            raise HTTPException(status_code=422, detail="Endereço da entrega sem coordenadas")

        eta = DriverEtaService(db, ctx.tenant_id).eta_to(
            driver_id=record.driver_id,
            destination=(record.address_lat, record.address_lng),
        )
        if not eta:
            raise HTTPException(status_code=404, detail="Sem posição do entregador")
        return eta
    finally:
        db.close()


# ── Rota otimizada (Fase 8) ────────────────────────────


@router.post("/route/optimize")
async def optimize_delivery_route(req: RouteOptimizeRequest, ctx: TenantContext = Depends(get_tenant_context)):
    """Reordena as entregas do entregador para minimizar a distância (Fase 8).

    - 409 quando a flag `DELIVERY_SMART_ROUTING_ENABLED` está desligada — não
      silenciar: quem pediu algo desligado precisa saber que está desligado;
    - 404 entregador inexistente/inativo, ou entrega fora do tenant (o filtro
      de tenant acontece no repositório — não vazamos existência);
    - 422 entregador sem posição conhecida, entrega sem coordenadas ou lista
      vazia: é a verdade do dado, não um erro de digitação.

    Publica `route.optimized` no barramento existente; o app do entregador
    reordena a lista ao receber (o payload traz `ordered_delivery_ids`).
    """
    from app.application.routing.optimizer import DeliveryRouteOptimizer
    from app.core.config import settings
    from app.domain.events.event_bus import EventType, publish_driver_event
    from app.infrastructure.repositories.delivery_persistence_repository import (
        SQLAlchemyDeliveryPersistenceRepository,
        SQLAlchemyDriverLocationRepository,
    )
    from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository
    from app.infrastructure.routing.factory import get_routing_provider

    if not settings.delivery_smart_routing_enabled:
        raise HTTPException(
            409,
            "Otimização de rota desligada (DELIVERY_SMART_ROUTING_ENABLED=false)",
        )

    db = _get_db()
    try:
        model = SQLAlchemyDeliveryDriverRepository(db, ctx.tenant_id).find_by_id_as_model(req.driver_id)
        if model is None or not model.ativo:
            raise HTTPException(404, "Entregador não encontrado")

        loc_repo = SQLAlchemyDriverLocationRepository(db)
        latest = loc_repo.latest_history_point(ctx.tenant_id, req.driver_id)
        if latest is None:
            latest = loc_repo.get_location(ctx.tenant_id, req.driver_id)
        if latest is None or latest.latitude is None or latest.longitude is None:
            raise HTTPException(422, "Entregador sem posição conhecida")

        del_repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx.tenant_id)
        points = []
        for delivery_id in req.delivery_ids:
            record = del_repo.get_delivery(delivery_id)
            if record is None:
                raise HTTPException(404, f"Entrega {delivery_id} não encontrada")
            if record.address_lat is None or record.address_lng is None:
                raise HTTPException(422, f"Entrega {delivery_id} sem coordenadas")
            points.append((delivery_id, float(record.address_lat), float(record.address_lng)))
        if not points:
            raise HTTPException(422, "Nenhuma entrega para otimizar")

        payload = DeliveryRouteOptimizer(get_routing_provider()).optimize(
            origin=(float(latest.latitude), float(latest.longitude)),
            deliveries=points,
        )
        result = {
            "driver_id": req.driver_id,
            "ordered_delivery_ids": payload.ordered_delivery_ids,
            "total_distance_km": payload.total_distance_km,
            "total_duration_s": payload.total_duration_s,
            "improvement_km": payload.improvement_km,
            "provider": payload.provider,
            "geometry": payload.geometry,
        }

        publish_driver_event(
            EventType.ROUTE_OPTIMIZED,
            req.driver_id,
            ctx.tenant_id,
            data={
                "driver_id": req.driver_id,
                "ordered_delivery_ids": payload.ordered_delivery_ids,
                "total_distance_km": payload.total_distance_km,
                "improvement_km": payload.improvement_km,
                "provider": payload.provider,
                "geometry": payload.geometry,
                "changed": payload.ordered_delivery_ids != req.delivery_ids,
            },
        )
        return result
    finally:
        db.close()


@router.get("/dispatch/candidates/{delivery_id}")
async def dispatch_candidates(delivery_id: str, ctx: TenantContext = Depends(get_tenant_context)):
    """Preview somente-leitura do score de despacho (Fase 9).

    Serve para o operador **entender** por que o sistema sugere quem sugere —
    o breakdown e os motivos vêm junto. Sem efeito colateral: só lê.
    """
    from app.application.dispatch.scorer import DispatchScorer
    from app.core.config import settings

    if not settings.delivery_smart_dispatch_enabled:
        raise HTTPException(
            409,
            "Score de despacho desligado (DELIVERY_SMART_DISPATCH_ENABLED=false)",
        )

    db = _get_db()
    try:
        try:
            scores = DispatchScorer(db, ctx.tenant_id).score(delivery_id=delivery_id)
        except LookupError:
            raise HTTPException(404, "Entrega não encontrada") from None
        return {
            "candidates": [
                {
                    "driver_id": s.driver_id,
                    "driver_name": s.driver_name,
                    "total": s.total,
                    "breakdown": s.breakdown,
                    "reasons": s.reasons,
                    "distance_km": s.distance_km,
                    "active_deliveries": s.active_deliveries,
                    "has_recent_position": s.has_recent_position,
                }
                for s in scores
            ]
        }
    finally:
        db.close()


# ── Gatilho automático pós-atribuição (Fase 8) ──────────


def _try_optimize_after_assign(tenant_id: str, driver_id: str) -> None:
    """Otimização best-effort da rota do entregador após atribuição.

    Chamado pelo endpoint de assign. Qualquer exceção é engolida — a
    atribuição NÃO pode falhar por causa da otimização.
    """
    try:
        from app.core.config import settings

        if not settings.delivery_smart_routing_enabled:
            return

        from app.application.routing.optimizer import DeliveryRouteOptimizer
        from app.domain.events.event_bus import EventType, publish_driver_event
        from app.infrastructure.database.init_db import engine
        from app.infrastructure.repositories.delivery_persistence_repository import (
            SQLAlchemyDeliveryPersistenceRepository,
            SQLAlchemyDriverLocationRepository,
        )
        from app.infrastructure.routing.factory import get_routing_provider
        from sqlalchemy.orm import Session as DBSession

        db = DBSession(bind=engine)
        try:
            del_repo = SQLAlchemyDeliveryPersistenceRepository(db, tenant_id)
            # Busca todas as entregas atribuídas a este entregador.
            from app.infrastructure.repositories.delivery_persistence_model import DeliveryRecord

            active_statuses = ("ASSIGNED", "DISPATCHED", "EN_ROUTE")
            deliveries = (
                db.query(DeliveryRecord)
                .filter(
                    DeliveryRecord.tenant_id == tenant_id,
                    DeliveryRecord.driver_id == driver_id,
                    DeliveryRecord.status.in_(active_statuses),
                )
                .order_by(DeliveryRecord.created_at.asc())
                .all()
            )
            if len(deliveries) < 2:
                # Uma ou nenhuma entrega: não há o que reordenar, mas
                # publicamos o evento para manter o app sincronizado.
                if deliveries:
                    publish_driver_event(
                        EventType.ROUTE_OPTIMIZED,
                        driver_id,
                        tenant_id,
                        data={
                            "driver_id": driver_id,
                            "ordered_delivery_ids": [d.delivery_id for d in deliveries],
                            "total_distance_km": 0.0,
                            "improvement_km": 0.0,
                            "provider": "haversine",
                            "changed": False,
                        },
                    )
                return

            # Posição do entregador.
            loc_repo = SQLAlchemyDriverLocationRepository(db)
            latest = loc_repo.latest_history_point(tenant_id, driver_id)
            if latest is None:
                latest = loc_repo.get_location(tenant_id, driver_id)
            if latest is None or latest.latitude is None or latest.longitude is None:
                return  # sem posição: nada a otimizar

            points = []
            for d in deliveries:
                if d.address_lat is not None and d.address_lng is not None:
                    points.append((d.delivery_id, float(d.address_lat), float(d.address_lng)))
            if len(points) < 2:
                return

            result = DeliveryRouteOptimizer(get_routing_provider()).optimize(
                origin=(float(latest.latitude), float(latest.longitude)),
                deliveries=points,
            )
            changed = result.ordered_delivery_ids != [d.delivery_id for d in deliveries]
            publish_driver_event(
                EventType.ROUTE_OPTIMIZED,
                driver_id,
                tenant_id,
                data={
                    "driver_id": driver_id,
                    "ordered_delivery_ids": result.ordered_delivery_ids,
                    "total_distance_km": result.total_distance_km,
                    "improvement_km": result.improvement_km,
                    "provider": result.provider,
                    "changed": changed,
                },
            )
        finally:
            db.close()
    except Exception:
        # Best-effort: loga e segue. A atribuição já foi confirmada.
        import logging

        logging.getLogger("gasflow.routing").debug("routing.optimize_after_assign.failed", exc_info=True)


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
        # Fase 3.3: distância do dia lida do histórico append-only (antes, só 0).
        for loc in locations:
            loc_driver = loc.get("driver_id")
            if loc_driver:
                loc["today_distance_km"] = loc_repo.today_distance_km(ctx.tenant_id, loc_driver)
        return {"locations": locations}
    finally:
        db.close()


# ── Backward-compat helper for printer/reports ─────────


def get_store():
    """Backward-compatible accessor — returns an empty dict.
    All real state is now in the database. This exists solely so
    that printer.py and reports.py don't crash on import."""
    return {}
