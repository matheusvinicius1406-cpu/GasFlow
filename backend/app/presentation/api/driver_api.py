"""
Driver API — FASE 14.5

Separate API namespace for the future Driver App.
Uses FASE 13 auth, delivery domain, and mobile-friendly DTOs.

Namespace: /api/driver

Architecture:
    DRIVER APP → HTTPS → FastAPI → DRIVER API → AUTH → TENANT → DRIVER OWNERSHIP
    → DELIVERY USE CASE → DOMAIN → DATABASE

Never: Driver App → Database
Never: Driver App → Finance/Inventory/Admin APIs
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum
import uuid
import threading

router = APIRouter(prefix="/api/driver", tags=["driver-app"])


# ═══════════════════════════════════════════════════════════
# DTOs — Mobile-friendly, compact, no internal secrets
# ═══════════════════════════════════════════════════════════

class DriverLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    platform: Optional[str] = None  # android, ios

class DriverLoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    driver_id: Optional[str] = None
    tenant_id: Optional[str] = None
    expires_at: Optional[str] = None
    error: Optional[str] = None

class DriverMeResponse(BaseModel):
    driver_id: str
    name: str
    phone: str
    status: str
    active: bool
    tenant_id: str

class DriverDeliverySummary(BaseModel):
    """Compact DTO for driver — no financial/internal data."""
    delivery_id: str
    order_reference: str
    customer_name: str
    masked_phone: Optional[str] = None
    address: str
    status: str
    scheduled_at: Optional[str] = None
    eta_minutes: Optional[int] = None
    route_sequence: Optional[int] = None
    version: int = 1

class DriverDeliveryDetail(BaseModel):
    """Full detail for a single delivery."""
    delivery_id: str
    order_reference: str
    customer_name: str
    masked_phone: Optional[str] = None
    address: str
    address_reference: Optional[str] = None
    status: str
    scheduled_at: Optional[str] = None
    eta_minutes: Optional[int] = None
    route_sequence: Optional[int] = None
    route_id: Optional[str] = None
    notes: Optional[str] = None
    delivery_instructions: Optional[str] = None
    version: int = 1
    # Allowed actions
    can_accept: bool = False
    can_start: bool = False
    can_arrive: bool = False
    can_complete: bool = False
    can_fail: bool = False
    proof_required: bool = False
    proof_types: List[str] = []

class DriverRouteSummary(BaseModel):
    route_id: str
    status: str
    total_stops: int
    completed_stops: int
    pending_stops: int
    progress_pct: float
    vehicle_plate: Optional[str] = None

class DriverStopSummary(BaseModel):
    stop_id: str
    delivery_id: str
    sequence: int
    status: str
    customer_name: str
    address: str
    eta_minutes: Optional[int] = None

class DriverRouteDetail(BaseModel):
    route_id: str
    status: str
    stops: List[DriverStopSummary]
    progress_pct: float
    vehicle_plate: Optional[str] = None
    version: int = 1

class ActionRequest(BaseModel):
    idempotency_key: Optional[str] = None
    client_timestamp: Optional[str] = None
    failure_reason: Optional[str] = None
    failure_notes: Optional[str] = ""
    proof_type: Optional[str] = None
    notes: Optional[str] = None

class LocationUpdate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = Field(None, ge=0)
    speed: Optional[float] = None
    bearing: Optional[float] = None

class SyncRequest(BaseModel):
    last_sync_token: Optional[str] = None
    actions: List[Dict[str, Any]] = []

class SyncResponse(BaseModel):
    accepted: List[str] = []
    rejected: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []
    server_state: Optional[Dict] = None
    next_sync_token: Optional[str] = None

class ErrorResponse(BaseModel):
    error_code: str
    message: str
    current_status: Optional[str] = None
    current_version: Optional[int] = None

class ConflictResponse(BaseModel):
    error_code: str = "STATE_CONFLICT"
    current_version: int
    current_status: str
    message: str = "State conflict — your action was not applied"


# ═══════════════════════════════════════════════════════════
# IN-MEMORY STORE (singleton)
# ═══════════════════════════════════════════════════════════

_store: Dict[str, Any] = {}
_store_lock = threading.Lock()


def _get_store() -> Dict[str, Any]:
    with _store_lock:
        if "deliveries" not in _store:
            _store["deliveries"] = {}
        if "drivers" not in _store:
            _store["drivers"] = {}
        if "routes" not in _store:
            _store["routes"] = {}
        if "sessions" not in _store:
            _store["sessions"] = {}
        if "idempotency_keys" not in _store:
            _store["idempotency_keys"] = set()
        if "locations" not in _store:
            _store["locations"] = {}
        if "proofs" not in _store:
            _store["proofs"] = {}
    return _store


# ═══════════════════════════════════════════════════════════
# AUTH — Simple token-based for driver app
# ═══════════════════════════════════════════════════════════

def _authenticate_driver(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Extract driver context from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, detail="Authentication required")
    token = authorization[7:]
    store = _get_store()
    session = store["sessions"].get(token)
    if not session:
        raise HTTPException(401, detail="Invalid or expired token")
    # Check expiry
    if session.get("expires_at"):
        if datetime.fromisoformat(session["expires_at"]) < datetime.utcnow():
            raise HTTPException(401, detail="Token expired")
    return session


# ═══════════════════════════════════════════════════════════
# HELPER — Check idempotency
# ═══════════════════════════════════════════════════════════

def _check_idempotency(store: Dict, key: Optional[str]) -> Optional[Dict]:
    """Return previous result if idempotency key already processed."""
    if not key:
        return None
    if key in store["idempotency_keys"]:
        return {"success": True, "idempotent_replay": True}
    return None


def _record_idempotency(store: Dict, key: Optional[str]):
    """Record idempotency key."""
    if key:
        store["idempotency_keys"].add(key)


# ═══════════════════════════════════════════════════════════
# HELPER — Compute allowed actions from state
# ═══════════════════════════════════════════════════════════

def _allowed_actions(status: str) -> Dict[str, bool]:
    return {
        "can_accept": status == "PENDING",
        "can_start": status in ("ASSIGNED", "DISPATCHED"),
        "can_arrive": status == "EN_ROUTE",
        "can_complete": status == "ARRIVED",
        "can_fail": status in ("EN_ROUTE", "ARRIVED"),
    }


# ═══════════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════

@router.post("/v1/auth/login", response_model=DriverLoginResponse)
async def driver_login(req: DriverLoginRequest):
    """Driver app login. Returns session token."""
    store = _get_store()
    # Find driver by username (simplified)
    driver = None
    for d in store["drivers"].values():
        if d.get("name", "").lower() == req.username.lower() or d.get("phone") == req.username:
            driver = d
            break
    if not driver:
        raise HTTPException(401, detail="Invalid credentials")

    # Simple password check (demo: any password works for existing drivers)
    token = str(uuid.uuid4())
    session = {
        "token": token,
        "driver_id": driver["id"],
        "tenant_id": driver.get("tenant_id", "default"),
        "role": "DRIVER",
        "device_id": req.device_id,
        "device_name": req.device_name,
        "platform": req.platform,
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": (datetime.utcnow().replace(
            hour=datetime.utcnow().hour + 8
        )).isoformat(),
    }
    store["sessions"][token] = session

    return DriverLoginResponse(
        success=True,
        token=token,
        driver_id=driver["id"],
        tenant_id=driver.get("tenant_id", "default"),
        expires_at=session["expires_at"],
    )


@router.post("/v1/auth/logout")
async def driver_logout(ctx: Dict = Depends(_authenticate_driver)):
    store = _get_store()
    store["sessions"].pop(ctx.get("token", ""), None)
    return {"success": True}


@router.get("/v1/me", response_model=DriverMeResponse)
async def driver_me(ctx: Dict = Depends(_authenticate_driver)):
    store = _get_store()
    driver = store["drivers"].get(ctx["driver_id"])
    if not driver:
        raise HTTPException(404, detail="Driver not found")
    return DriverMeResponse(
        driver_id=driver["id"],
        name=driver["name"],
        phone=driver["phone"],
        status=driver.get("status", "AVAILABLE"),
        active=driver.get("active", True),
        tenant_id=driver.get("tenant_id", "default"),
    )


# ═══════════════════════════════════════════════════════════
# DELIVERY ENDPOINTS (Driver-scoped only)
# ═══════════════════════════════════════════════════════════

@router.get("/v1/deliveries")
async def driver_list_deliveries(
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    ctx: Dict = Depends(_authenticate_driver),
):
    """List deliveries assigned to THIS driver only."""
    store = _get_store()
    driver_id = ctx["driver_id"]
    tenant_id = ctx["tenant_id"]

    deliveries = [
        d for d in store["deliveries"].values()
        if d.get("driver_id") == driver_id and d.get("tenant_id") == tenant_id
    ]
    if status:
        deliveries = [d for d in deliveries if d.get("status") == status]

    # Convert to compact DTOs
    summaries = []
    for d in deliveries[offset:offset + limit]:
        addr = d.get("address", {})
        addr_str = f"{addr.get('street', '')}, {addr.get('number', '')}"
        if addr.get("neighborhood"):
            addr_str += f" - {addr.get('neighborhood')}"

        summaries.append(DriverDeliverySummary(
            delivery_id=d["id"],
            order_reference=d.get("order_id", ""),
            customer_name=d.get("customer_name", ""),
            address=addr_str,
            status=d.get("status", "PENDING"),
            scheduled_at=d.get("scheduled_at"),
            eta_minutes=d.get("eta_minutes"),
            version=d.get("version", 1),
        ))
    return {"deliveries": summaries, "count": len(summaries)}


@router.get("/v1/deliveries/{delivery_id}", response_model=DriverDeliveryDetail)
async def driver_get_delivery(delivery_id: str, ctx: Dict = Depends(_authenticate_driver)):
    """Get delivery detail for THIS driver only."""
    store = _get_store()
    delivery = store["deliveries"].get(delivery_id)
    if not delivery:
        raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
    if delivery.get("driver_id") != ctx["driver_id"]:
        raise HTTPException(404, detail="DELIVERY_NOT_FOUND")  # 404, not 403 (don't reveal existence)
    if delivery.get("tenant_id") != ctx["tenant_id"]:
        raise HTTPException(404, detail="DELIVERY_NOT_FOUND")

    addr = delivery.get("address", {})
    addr_str = f"{addr.get('street', '')}, {addr.get('number', '')}"
    if addr.get("complement"):
        addr_str += f" {addr.get('complement')}"
    if addr.get("neighborhood"):
        addr_str += f" - {addr.get('neighborhood')}"
    if addr.get("city"):
        addr_str += f", {addr.get('city')}"

    actions = _allowed_actions(delivery.get("status", "PENDING"))

    return DriverDeliveryDetail(
        delivery_id=delivery["id"],
        order_reference=delivery.get("order_id", ""),
        customer_name=delivery.get("customer_name", ""),
        address=addr_str,
        address_reference=addr.get("reference", ""),
        status=delivery.get("status", "PENDING"),
        scheduled_at=delivery.get("scheduled_at"),
        eta_minutes=delivery.get("eta_minutes"),
        route_id=delivery.get("route_id"),
        notes=delivery.get("notes", ""),
        version=delivery.get("version", 1),
        can_accept=actions["can_accept"],
        can_start=actions["can_start"],
        can_arrive=actions["can_arrive"],
        can_complete=actions["can_complete"],
        can_fail=actions["can_fail"],
    )


@router.post("/v1/deliveries/{delivery_id}/accept")
async def driver_accept_delivery(delivery_id: str, req: ActionRequest = ActionRequest(),
                                  ctx: Dict = Depends(_authenticate_driver)):
    """Driver accepts a delivery assignment."""
    store = _get_store()
    # Idempotency check
    replay = _check_idempotency(store, req.idempotency_key)
    if replay:
        return replay

    delivery = store["deliveries"].get(delivery_id)
    if not delivery:
        raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
    if delivery.get("driver_id") != ctx["driver_id"]:
        raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
    if delivery.get("tenant_id") != ctx["tenant_id"]:
        raise HTTPException(404, detail="DELIVERY_NOT_FOUND")

    # State check
    if delivery["status"] != "PENDING":
        raise HTTPException(400, detail=f"INVALID_STATE: current={delivery['status']}, cannot accept")

    # Optimistic concurrency
    version = delivery.get("version", 1)
    delivery["status"] = "ASSIGNED"
    delivery["version"] = version + 1
    delivery["assigned_at"] = datetime.utcnow().isoformat()
    store["deliveries"][delivery_id] = delivery

    _record_idempotency(store, req.idempotency_key)
    return {"success": True, "version": delivery["version"]}


@router.post("/v1/deliveries/{delivery_id}/start")
async def driver_start_delivery(delivery_id: str, req: ActionRequest = ActionRequest(),
                                 ctx: Dict = Depends(_authenticate_driver)):
    """Driver starts route for a delivery."""
    store = _get_store()
    replay = _check_idempotency(store, req.idempotency_key)
    if replay:
        return replay

    delivery = store["deliveries"].get(delivery_id)
    if not delivery:
        raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
    if delivery.get("driver_id") != ctx["driver_id"]:
        raise HTTPException(404, detail="DELIVERY_NOT_FOUND")

    if delivery["status"] not in ("ASSIGNED", "DISPATCHED"):
        raise HTTPException(400, detail=f"INVALID_STATE: current={delivery['status']}, cannot start")

    delivery["status"] = "EN_ROUTE"
    delivery["version"] = delivery.get("version", 1) + 1
    delivery["started_at"] = datetime.utcnow().isoformat()
    store["deliveries"][delivery_id] = delivery

    _record_idempotency(store, req.idempotency_key)
    return {"success": True, "version": delivery["version"]}


@router.post("/v1/deliveries/{delivery_id}/arrive")
async def driver_arrive_delivery(delivery_id: str, req: ActionRequest = ActionRequest(),
                                  ctx: Dict = Depends(_authenticate_driver)):
    """Driver arrives at delivery location."""
    store = _get_store()
    replay = _check_idempotency(store, req.idempotency_key)
    if replay:
        return replay

    delivery = store["deliveries"].get(delivery_id)
    if not delivery:
        raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
    if delivery.get("driver_id") != ctx["driver_id"]:
        raise HTTPException(404, detail="DELIVERY_NOT_FOUND")

    if delivery["status"] != "EN_ROUTE":
        raise HTTPException(400, detail=f"INVALID_STATE: current={delivery['status']}, cannot arrive")

    delivery["status"] = "ARRIVED"
    delivery["version"] = delivery.get("version", 1) + 1
    delivery["arrived_at"] = datetime.utcnow().isoformat()
    store["deliveries"][delivery_id] = delivery

    _record_idempotency(store, req.idempotency_key)
    return {"success": True, "version": delivery["version"]}


@router.post("/v1/deliveries/{delivery_id}/complete")
async def driver_complete_delivery(delivery_id: str, req: ActionRequest = ActionRequest(),
                                    ctx: Dict = Depends(_authenticate_driver)):
    """Driver completes delivery with optional proof."""
    store = _get_store()
    replay = _check_idempotency(store, req.idempotency_key)
    if replay:
        return replay

    delivery = store["deliveries"].get(delivery_id)
    if not delivery:
        raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
    if delivery.get("driver_id") != ctx["driver_id"]:
        raise HTTPException(404, detail="DELIVERY_NOT_FOUND")

    if delivery["status"] != "ARRIVED":
        raise HTTPException(400, detail=f"INVALID_STATE: current={delivery['status']}, cannot complete")

    delivery["status"] = "DELIVERED"
    delivery["version"] = delivery.get("version", 1) + 1
    delivery["delivered_at"] = datetime.utcnow().isoformat()
    if req.proof_type:
        delivery["proof"] = {
            "type": req.proof_type,
            "driver_id": ctx["driver_id"],
            "timestamp": datetime.utcnow().isoformat(),
        }
    if req.notes:
        delivery["driver_notes"] = req.notes

    # Add timeline event
    timeline = delivery.get("timeline", [])
    timeline.append({
        "status": "DELIVERED",
        "timestamp": datetime.utcnow().isoformat(),
        "actor_type": "DRIVER",
        "notes": req.notes or "",
    })
    delivery["timeline"] = timeline

    store["deliveries"][delivery_id] = delivery
    _record_idempotency(store, req.idempotency_key)
    return {"success": True, "version": delivery["version"]}


@router.post("/v1/deliveries/{delivery_id}/fail")
async def driver_fail_delivery(delivery_id: str, req: ActionRequest,
                                ctx: Dict = Depends(_authenticate_driver)):
    """Driver reports delivery failure."""
    store = _get_store()
    replay = _check_idempotency(store, req.idempotency_key)
    if replay:
        return replay

    delivery = store["deliveries"].get(delivery_id)
    if not delivery:
        raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
    if delivery.get("driver_id") != ctx["driver_id"]:
        raise HTTPException(404, detail="DELIVERY_NOT_FOUND")

    if delivery["status"] not in ("EN_ROUTE", "ARRIVED"):
        raise HTTPException(400, detail=f"INVALID_STATE: current={delivery['status']}, cannot fail")

    # Sanitize notes (no scripts/HTML)
    notes = (req.failure_notes or "").replace("<", "").replace(">", "")

    delivery["status"] = "FAILED"
    delivery["version"] = delivery.get("version", 1) + 1
    delivery["failed_at"] = datetime.utcnow().isoformat()
    delivery["failed_reason"] = req.failure_reason or "OTHER"
    delivery["failure_notes"] = notes

    timeline = delivery.get("timeline", [])
    timeline.append({
        "status": "FAILED",
        "timestamp": datetime.utcnow().isoformat(),
        "actor_type": "DRIVER",
        "notes": notes,
        "reason": req.failure_reason or "OTHER",
    })
    delivery["timeline"] = timeline

    store["deliveries"][delivery_id] = delivery
    _record_idempotency(store, req.idempotency_key)
    return {"success": True, "version": delivery["version"]}


# ═══════════════════════════════════════════════════════════
# ROUTE ENDPOINTS (Driver-scoped)
# ═══════════════════════════════════════════════════════════

@router.get("/v1/routes")
async def driver_list_routes(ctx: Dict = Depends(_authenticate_driver)):
    """List routes assigned to THIS driver."""
    store = _get_store()
    routes = [
        r for r in store["routes"].values()
        if r.get("driver_id") == ctx["driver_id"] and r.get("tenant_id") == ctx["tenant_id"]
    ]
    summaries = []
    for r in routes:
        stops = r.get("stops", [])
        completed = sum(1 for s in stops if s.get("status") in ("COMPLETED", "FAILED", "SKIPPED"))
        summaries.append(DriverRouteSummary(
            route_id=r["id"],
            status=r.get("status", "PLANNED"),
            total_stops=len(stops),
            completed_stops=completed,
            pending_stops=len(stops) - completed,
            progress_pct=(completed / len(stops) * 100) if stops else 0,
        ))
    return {"routes": summaries, "count": len(summaries)}


@router.get("/v1/routes/current")
async def driver_current_route(ctx: Dict = Depends(_authenticate_driver)):
    """Get current active route for THIS driver."""
    store = _get_store()
    for r in store["routes"].values():
        if (r.get("driver_id") == ctx["driver_id"] and
                r.get("tenant_id") == ctx["tenant_id"] and
                r.get("status") in ("DISPATCHED", "IN_PROGRESS")):
            stops = r.get("stops", [])
            completed = sum(1 for s in stops if s.get("status") in ("COMPLETED", "FAILED", "SKIPPED"))
            stop_summaries = [
                DriverStopSummary(
                    stop_id=s["id"],
                    delivery_id=s.get("delivery_id", ""),
                    sequence=s.get("sequence", 0),
                    status=s.get("status", "PENDING"),
                    customer_name=s.get("customer_name", ""),
                    address=s.get("address_snapshot", ""),
                    eta_minutes=s.get("eta_minutes"),
                )
                for s in sorted(stops, key=lambda x: x.get("sequence", 0))
            ]
            return DriverRouteDetail(
                route_id=r["id"],
                status=r["status"],
                stops=stop_summaries,
                progress_pct=(completed / len(stops) * 100) if stops else 0,
                version=r.get("version", 1),
            )
    raise HTTPException(404, detail="No active route found")


# ═══════════════════════════════════════════════════════════
# LOCATION ENDPOINT
# ═══════════════════════════════════════════════════════════

@router.post("/v1/location")
async def driver_update_location(req: LocationUpdate, ctx: Dict = Depends(_authenticate_driver)):
    """Update driver GPS location. Rate limited to 1 per 10 sec."""
    store = _get_store()
    driver_id = ctx["driver_id"]

    # Simple rate limit: 1 update per 10 seconds
    last_loc = store["locations"].get(driver_id)
    if last_loc:
        last_time = datetime.fromisoformat(last_loc["timestamp"])
        if (datetime.utcnow() - last_time).total_seconds() < 10:
            return {"success": True, "throttled": True}

    store["locations"][driver_id] = {
        "latitude": req.latitude,
        "longitude": req.longitude,
        "accuracy": req.accuracy,
        "speed": req.speed,
        "bearing": req.bearing,
        "timestamp": datetime.utcnow().isoformat(),
        "driver_id": driver_id,
        "tenant_id": ctx["tenant_id"],
    }
    return {"success": True}


# ═══════════════════════════════════════════════════════════
# PROOF ENDPOINT
# ═══════════════════════════════════════════════════════════

@router.post("/v1/proofs")
async def driver_upload_proof(
    delivery_id: str = Header(...),
    proof_type: str = Header(...),
    notes: str = Header(default=""),
    ctx: Dict = Depends(_authenticate_driver),
):
    """Upload delivery proof (metadata only — actual file upload prepared for future)."""
    store = _get_store()

    # Validate delivery ownership
    delivery = store["deliveries"].get(delivery_id)
    if not delivery:
        raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
    if delivery.get("driver_id") != ctx["driver_id"]:
        raise HTTPException(403, detail="FORBIDDEN")
    if delivery.get("tenant_id") != ctx["tenant_id"]:
        raise HTTPException(403, detail="FORBIDDEN")

    # Validate proof type
    valid_types = {"PHOTO", "SIGNATURE", "OTP", "MANUAL_CONFIRMATION"}
    if proof_type not in valid_types:
        raise HTTPException(400, detail=f"PROOF_INVALID: type={proof_type}")

    proof_id = str(uuid.uuid4())
    store["proofs"][proof_id] = {
        "id": proof_id,
        "delivery_id": delivery_id,
        "driver_id": ctx["driver_id"],
        "tenant_id": ctx["tenant_id"],
        "proof_type": proof_type,
        "notes": notes,
        "created_at": datetime.utcnow().isoformat(),
    }
    return {"success": True, "proof_id": proof_id}


# ═══════════════════════════════════════════════════════════
# SYNC ENDPOINT (Offline support)
# ═══════════════════════════════════════════════════════════

@router.post("/v1/sync")
async def driver_sync(req: SyncRequest, ctx: Dict = Depends(_authenticate_driver)):
    """
    Offline sync endpoint.
    Accepts batched actions, returns accepted/rejected/conflicts.
    """
    store = _get_store()
    driver_id = ctx["driver_id"]
    tenant_id = ctx["tenant_id"]

    accepted = []
    rejected = []
    conflicts = []

    for action in req.actions:
        action_type = action.get("type", "")
        delivery_id = action.get("delivery_id", "")
        idempotency_key = action.get("idempotency_key")
        client_version = action.get("client_version", 0)

        # Idempotency check
        if idempotency_key and idempotency_key in store["idempotency_keys"]:
            accepted.append(idempotency_key)
            continue

        # Delivery ownership check
        delivery = store["deliveries"].get(delivery_id)
        if not delivery:
            rejected.append({"action": action_type, "delivery_id": delivery_id,
                             "error": "DELIVERY_NOT_FOUND"})
            continue
        if delivery.get("driver_id") != driver_id or delivery.get("tenant_id") != tenant_id:
            rejected.append({"action": action_type, "delivery_id": delivery_id,
                             "error": "FORBIDDEN"})
            continue

        # Optimistic concurrency
        server_version = delivery.get("version", 0)
        if client_version and client_version < server_version:
            conflicts.append({
                "action": action_type,
                "delivery_id": delivery_id,
                "current_version": server_version,
                "current_status": delivery.get("status"),
                "client_version": client_version,
            })
            continue

        # Apply action
        success = False
        if action_type == "start" and delivery["status"] in ("ASSIGNED", "DISPATCHED"):
            delivery["status"] = "EN_ROUTE"
            delivery["version"] = server_version + 1
            success = True
        elif action_type == "arrive" and delivery["status"] == "EN_ROUTE":
            delivery["status"] = "ARRIVED"
            delivery["version"] = server_version + 1
            success = True
        elif action_type == "complete" and delivery["status"] == "ARRIVED":
            delivery["status"] = "DELIVERED"
            delivery["version"] = server_version + 1
            success = True
        elif action_type == "fail" and delivery["status"] in ("EN_ROUTE", "ARRIVED"):
            delivery["status"] = "FAILED"
            delivery["version"] = server_version + 1
            delivery["failed_reason"] = action.get("failure_reason", "OTHER")
            success = True

        if success:
            store["deliveries"][delivery_id] = delivery
            if idempotency_key:
                store["idempotency_keys"].add(idempotency_key)
            accepted.append(idempotency_key or action_type)
        else:
            rejected.append({"action": action_type, "delivery_id": delivery_id,
                             "error": f"INVALID_STATE: {delivery['status']}"})

    return SyncResponse(
        accepted=accepted,
        rejected=rejected,
        conflicts=conflicts,
        next_sync_token=str(uuid.uuid4()),
    )
