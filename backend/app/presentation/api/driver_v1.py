"""
Driver API v1 — Central API Namespace

Official driver endpoints under /api/v1/driver/*.
Uses shared handler functions from driver_api.py.

This is the OFFICIAL namespace for the Driver App (entregadorGasFlow).
The legacy /api/driver/v1/* routes are maintained for backward compatibility.
"""

from fastapi import APIRouter, Depends, Header
from typing import Optional
from app.presentation.api.driver_api import (
    # Handlers
    handle_driver_login,
    handle_driver_logout,
    handle_driver_me,
    handle_list_deliveries,
    handle_get_delivery,
    handle_accept_delivery,
    handle_start_delivery,
    handle_arrive_delivery,
    handle_complete_delivery,
    handle_fail_delivery,
    handle_list_routes,
    handle_current_route,
    handle_update_location,
    handle_upload_proof,
    handle_sync,
    # Auth dependency
    _authenticate_driver,
    # DTOs
    DriverLoginRequest,
    DriverLoginResponse,
    DriverMeResponse,
    DriverDeliverySummary,
    DriverDeliveryDetail,
    DriverRouteSummary,
    DriverRouteDetail,
    DriverStopSummary,
    ActionRequest,
    LocationUpdate,
    SyncRequest,
    SyncResponse,
)

# Official v1 router: /api/v1/driver/*
router = APIRouter(prefix="/driver", tags=["driver-v1"])


# ═══════════════════════════════════════════════════════════
# Auth — /api/v1/driver/auth/*
# ═══════════════════════════════════════════════════════════

@router.post("/auth/login", response_model=DriverLoginResponse, summary="Driver login")
async def v1_driver_login(req: DriverLoginRequest):
    """Driver app login. Returns session token."""
    return await handle_driver_login(req)


@router.post("/auth/logout", summary="Driver logout")
async def v1_driver_logout(ctx: dict = Depends(_authenticate_driver)):
    """Driver app logout. Clears session."""
    return await handle_driver_logout(ctx)


@router.get("/me", response_model=DriverMeResponse, summary="Driver profile")
async def v1_driver_me(ctx: dict = Depends(_authenticate_driver)):
    """Get authenticated driver profile."""
    return await handle_driver_me(ctx)


# ═══════════════════════════════════════════════════════════
# Deliveries — /api/v1/driver/deliveries/*
# ═══════════════════════════════════════════════════════════

@router.get("/deliveries", summary="List my deliveries")
async def v1_driver_list_deliveries(
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    ctx: dict = Depends(_authenticate_driver),
):
    """List deliveries assigned to THIS driver only."""
    return await handle_list_deliveries(ctx, status=status, limit=limit, offset=offset)


@router.get("/deliveries/{delivery_id}", response_model=DriverDeliveryDetail, summary="Delivery detail")
async def v1_driver_get_delivery(
    delivery_id: str,
    ctx: dict = Depends(_authenticate_driver),
):
    """Get delivery detail for THIS driver only."""
    return await handle_get_delivery(ctx, delivery_id)


@router.post("/deliveries/{delivery_id}/accept", summary="Accept delivery")
async def v1_driver_accept_delivery(
    delivery_id: str,
    req: ActionRequest = ActionRequest(),
    ctx: dict = Depends(_authenticate_driver),
):
    """Driver accepts a delivery assignment."""
    return await handle_accept_delivery(ctx, delivery_id, req)


@router.post("/deliveries/{delivery_id}/start", summary="Start route")
async def v1_driver_start_delivery(
    delivery_id: str,
    req: ActionRequest = ActionRequest(),
    ctx: dict = Depends(_authenticate_driver),
):
    """Driver starts route for a delivery."""
    return await handle_start_delivery(ctx, delivery_id, req)


@router.post("/deliveries/{delivery_id}/arrive", summary="Arrive at location")
async def v1_driver_arrive_delivery(
    delivery_id: str,
    req: ActionRequest = ActionRequest(),
    ctx: dict = Depends(_authenticate_driver),
):
    """Driver arrives at delivery location."""
    return await handle_arrive_delivery(ctx, delivery_id, req)


@router.post("/deliveries/{delivery_id}/complete", summary="Complete delivery")
async def v1_driver_complete_delivery(
    delivery_id: str,
    req: ActionRequest = ActionRequest(),
    ctx: dict = Depends(_authenticate_driver),
):
    """Driver completes delivery with optional proof."""
    return await handle_complete_delivery(ctx, delivery_id, req)


@router.post("/deliveries/{delivery_id}/fail", summary="Report failure")
async def v1_driver_fail_delivery(
    delivery_id: str,
    req: ActionRequest,
    ctx: dict = Depends(_authenticate_driver),
):
    """Driver reports delivery failure."""
    return await handle_fail_delivery(ctx, delivery_id, req)


# ═══════════════════════════════════════════════════════════
# Routes — /api/v1/driver/routes/*
# ═══════════════════════════════════════════════════════════

@router.get("/routes", summary="List my routes")
async def v1_driver_list_routes(ctx: dict = Depends(_authenticate_driver)):
    """List routes assigned to THIS driver."""
    return await handle_list_routes(ctx)


@router.get("/routes/current", summary="Current active route")
async def v1_driver_current_route(ctx: dict = Depends(_authenticate_driver)):
    """Get current active route for THIS driver."""
    return await handle_current_route(ctx)


# ═══════════════════════════════════════════════════════════
# Location — /api/v1/driver/location
# ═══════════════════════════════════════════════════════════

@router.post("/location", summary="Update GPS location")
async def v1_driver_update_location(
    req: LocationUpdate,
    ctx: dict = Depends(_authenticate_driver),
):
    """Update driver GPS location. Rate limited to 1 per 10 sec."""
    return await handle_update_location(ctx, req)


# ═══════════════════════════════════════════════════════════
# Proofs — /api/v1/driver/proofs
# ═══════════════════════════════════════════════════════════

@router.post("/proofs", summary="Upload delivery proof")
async def v1_driver_upload_proof(
    delivery_id: str = Header(...),
    proof_type: str = Header(...),
    notes: str = Header(default=""),
    ctx: dict = Depends(_authenticate_driver),
):
    """Upload delivery proof (metadata only)."""
    return await handle_upload_proof(ctx, delivery_id, proof_type, notes)


# ═══════════════════════════════════════════════════════════
# Sync — /api/v1/driver/sync
# ═══════════════════════════════════════════════════════════

@router.post("/sync", summary="Offline sync")
async def v1_driver_sync(
    req: SyncRequest,
    ctx: dict = Depends(_authenticate_driver),
):
    """Offline sync endpoint."""
    return await handle_sync(ctx, req)
