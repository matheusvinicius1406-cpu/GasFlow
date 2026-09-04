"""
Dispatch API — Intelligent Delivery Assignment

POST /api/v1/dispatch/recommend  → Get dispatch recommendations
POST /api/v1/dispatch/assign     → Assign driver to delivery
GET  /api/v1/dispatch/status     → Dispatch dashboard summary
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

from app.domain.delivery.dispatch_engine import (
    DispatchEngine, DispatchMode, OrderRequest, DriverCandidate, OrderItem,
)
from app.presentation.dependencies import get_tenant_context, require_admin
from app.domain.security.models import TenantContext

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


# ── Schemas ──────────────────────────────────────────────

class DispatchItemRequest(BaseModel):
    product_codigo: str
    product_name: str
    quantity: int = Field(..., gt=0)


class DispatchOrderRequest(BaseModel):
    order_id: str
    customer_codigo: str = ""
    customer_name: str = ""
    items: List[DispatchItemRequest] = []
    priority: int = 0
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    scheduled_at: Optional[str] = None
    notes: str = ""


class DriverCandidateRequest(BaseModel):
    driver_id: str
    driver_name: str
    vehicle_id: Optional[str] = None
    vehicle_plate: Optional[str] = None
    status: str = "AVAILABLE"
    is_active: bool = True
    is_paused: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    last_seen: Optional[str] = None
    capacity: Dict[str, int] = {}    # {product_codigo: available}
    current_load: Dict[str, int] = {}  # {product_codigo: loaded}
    active_deliveries: int = 0
    current_route_lat: Optional[float] = None
    current_route_lng: Optional[float] = None


class DispatchRecommendRequest(BaseModel):
    order: DispatchOrderRequest
    candidates: List[DriverCandidateRequest] = []


class AssignRequest(BaseModel):
    delivery_id: str
    driver_id: str
    vehicle_id: Optional[str] = None




# ── Endpoints ────────────────────────────────────────────

@router.post("/recommend")
async def get_dispatch_recommendations(
    req: DispatchRecommendRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Get intelligent dispatch recommendations.

    Analyzes candidates and returns ranked recommendations
    with capacity fit, distance, and explanations.
    """
    engine = DispatchEngine(mode=DispatchMode.ASSISTED)

    # Build order request
    order = OrderRequest(
        order_id=req.order.order_id,
        tenant_id="default",
        customer_codigo=req.order.customer_codigo,
        customer_name=req.order.customer_name,
        items=[
            OrderItem(
                product_codigo=item.product_codigo,
                product_name=item.product_name,
                quantity=item.quantity,
            )
            for item in req.order.items
        ],
        priority=req.order.priority,
        latitude=req.order.latitude,
        longitude=req.order.longitude,
        notes=req.order.notes,
    )

    # Build candidates
    candidates = [
        DriverCandidate(
            driver_id=c.driver_id,
            driver_name=c.driver_name,
            vehicle_id=c.vehicle_id,
            vehicle_plate=c.vehicle_plate,
            status=c.status,
            is_active=c.is_active,
            is_paused=c.is_paused,
            latitude=c.latitude,
            longitude=c.longitude,
            capacity=c.capacity,
            current_load=c.current_load,
            active_deliveries=c.active_deliveries,
            current_route_lat=c.current_route_lat,
            current_route_lng=c.current_route_lng,
        )
        for c in req.candidates
    ]

    result = engine.recommend(order, candidates)
    return result


@router.post("/assign")
async def assign_driver_to_delivery(
    req: AssignRequest,
    ctx: TenantContext = Depends(require_admin),
):
    """
    Assign a driver to a delivery.
    Uses AssignmentService for transactional assignment.
    """
    from app.infrastructure.database.init_db import engine
    from sqlalchemy.orm import Session
    from app.application.delivery.assignment_service import AssignmentService

    db = Session(bind=engine)
    try:
        service = AssignmentService(db)
        result = service.assign(
            tenant_id=ctx.tenant_id,
            delivery_id=req.delivery_id,
            driver_codigo=req.driver_id,
            vehicle_id=int(req.vehicle_id) if req.vehicle_id else None,
        )
        return result
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        raise HTTPException(500, detail=f"Assignment failed: {e}")
    finally:
        db.close()


@router.get("/status")
async def dispatch_status(
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get dispatch dashboard summary."""
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository
    from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository

    db = DBSession(bind=engine)
    try:
        del_repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx.tenant_id)
        drv_repo = SQLAlchemyDeliveryDriverRepository(db, ctx.tenant_id)

        status_counts = del_repo.count_by_status()
        total_deliveries = sum(status_counts.values())

        drivers = drv_repo.listar_todos()
        total_drivers = len(drivers)
        available_drivers = sum(1 for d in drivers if d.is_available)
        online_drivers = sum(1 for d in drivers if d.status.value not in ("OFFLINE", "INACTIVE"))

        return {
            "deliveries": {
                "total": total_deliveries,
                "by_status": status_counts,
            },
            "drivers": {
                "total": total_drivers,
                "available": available_drivers,
                "online": online_drivers,
            },
            "vehicles": {
                "total": 0,
                "by_status": {},
                "available": 0,
                "with_capacity": 0,
            },
        }
    finally:
        db.close()
