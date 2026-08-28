"""
Dispatch API — Intelligent Delivery Assignment

POST /api/v1/dispatch/recommend  → Get dispatch recommendations
POST /api/v1/dispatch/assign     → Assign driver to delivery
GET  /api/v1/dispatch/status     → Dispatch dashboard summary
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime

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


# ── In-memory store for demo (same as delivery_ops) ──────

_in_memory_store = {}


def _get_store():
    return _in_memory_store


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
    Validates eligibility and updates both entities.
    """
    store = _get_store()

    # Find delivery
    delivery = store.get("deliveries", {}).get(req.delivery_id)
    if not delivery:
        raise HTTPException(404, "Delivery not found")

    # Find driver
    driver = store.get("drivers", {}).get(req.driver_id)
    if not driver:
        raise HTTPException(404, "Driver not found")

    # Check driver is available
    if not driver.is_available:
        raise HTTPException(400, f"Driver is {driver.status.value}")

    # Check vehicle capacity if items are specified
    if req.vehicle_id:
        vehicle = store.get("vehicles", {}).get(req.vehicle_id)
        if vehicle:
            # Check capacity (simplified for in-memory)
            pass

    # Assign
    if not delivery.assign(req.driver_id, req.vehicle_id):
        raise HTTPException(400, f"Cannot assign in status {delivery.status.value}")

    driver.set_busy()

    return {
        "success": True,
        "delivery": delivery.to_dict(),
        "driver": driver.to_dict(),
    }


@router.get("/status")
async def dispatch_status(
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get dispatch dashboard summary."""
    store = _get_store()
    tenant_id = "default"

    deliveries = [d for d in store.get("deliveries", {}).values()
                  if getattr(d, 'tenant_id', '') == tenant_id]
    drivers = [d for d in store.get("drivers", {}).values()
               if getattr(d, 'tenant_id', '') == tenant_id]
    vehicles = [v for v in store.get("vehicles", {}).values()
                if getattr(v, 'tenant_id', '') == tenant_id]

    # Delivery stats
    delivery_stats = {}
    for d in deliveries:
        status = getattr(d, 'status', None)
        s = status.value if hasattr(status, 'value') else str(status)
        delivery_stats[s] = delivery_stats.get(s, 0) + 1

    # Driver stats
    driver_stats = {}
    for d in drivers:
        status = getattr(d, 'status', None)
        s = status.value if hasattr(status, 'value') else str(status)
        driver_stats[s] = driver_stats.get(s, 0) + 1

    # Vehicle stats
    vehicle_stats = {}
    for v in vehicles:
        status = getattr(v, 'status', None)
        s = status.value if hasattr(status, 'value') else str(status)
        vehicle_stats[s] = vehicle_stats.get(s, 0) + 1

    return {
        "deliveries": {
            "total": len(deliveries),
            "by_status": delivery_stats,
        },
        "drivers": {
            "total": len(drivers),
            "by_status": driver_stats,
            "available": sum(1 for d in drivers if getattr(d, 'is_available', False)),
            "online": sum(1 for d in drivers if getattr(d, 'status', None) and
                         d.status.value not in ("OFFLINE", "INACTIVE")),
        },
        "vehicles": {
            "total": len(vehicles),
            "by_status": vehicle_stats,
            "available": sum(1 for v in vehicles if getattr(v, 'is_available', False)),
            "with_capacity": sum(1 for v in vehicles if getattr(v, 'has_capacity', False)),
        },
    }
