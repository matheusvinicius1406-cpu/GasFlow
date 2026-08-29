"""
Driver API — FASE 14.5

Driver-facing API endpoints for the entregadorGasFlow mobile app.
Uses token-based auth, tenant isolation, and delivery ownership checks.

This module defines:
- DTOs (Data Transfer Objects) for driver communication
- Authentication dependency
- Idempotency helpers
- State machine helpers
- In-memory store (demo; replace with real DB in production)

Route definitions live in two files:
- driver_api.py  → legacy /api/driver/v1/* (backward compatibility)
- driver_v1.py   → official /api/v1/driver/* (central API)

Architecture:
    DRIVER APP → HTTPS → FastAPI → DRIVER API → AUTH → TENANT → DRIVER OWNERSHIP
    → DELIVERY USE CASE → DOMAIN → DATABASE

Never: Driver App → Database
Never: Driver App → Finance/Inventory/Admin APIs
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from enum import Enum
import uuid
import bcrypt
from app.infrastructure.stores.shared_store import get_shared_store
from app.domain.events.event_bus import (
    get_event_bus, publish_delivery_event, publish_driver_event, EventType
)
from sqlalchemy.orm import Session as DBSession
from app.infrastructure.database.init_db import engine


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
# SHARED STORE (single source of truth)
# ═══════════════════════════════════════════════════════════

def _get_store() -> Dict[str, Any]:
    return get_shared_store()


def _get_db() -> DBSession:
    """Get a new database session."""
    return DBSession(bind=engine)


# ═══════════════════════════════════════════════════════════
# AUTH — Persistent token-based for driver app
# ═══════════════════════════════════════════════════════════

def _authenticate_driver(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Extract driver context from Authorization header.

    Database is the single source of truth for sessions.
    No in-memory fallback — DB failure returns controlled error.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, detail="Authentication required")
    token = authorization[7:]

    db = _get_db()
    try:
        from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDriverSessionRepository
        session_repo = SQLAlchemyDriverSessionRepository(db)
        record = session_repo.get_session(token)
        if not record:
            raise HTTPException(401, detail="Invalid or expired token")
        # Check expiry
        if record.expires_at and record.expires_at < datetime.utcnow():
            raise HTTPException(401, detail="Token expired")
        return record.to_dict()
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# HELPER — Check idempotency
# ═══════════════════════════════════════════════════════════

def _check_idempotency(key: Optional[str]) -> Optional[Dict]:
    """Return previous result if idempotency key already processed.

    Database is the single source of truth.
    No in-memory fallback — DB failure returns None (allow processing).
    """
    if not key:
        return None

    db = _get_db()
    try:
        from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyIdempotencyRepository
        idem_repo = SQLAlchemyIdempotencyRepository(db)
        if idem_repo.exists(key):
            return {"success": True, "idempotent_replay": True}
    finally:
        db.close()
    return None


def _record_idempotency(key: Optional[str]):
    """Record idempotency key to database."""
    if key:
        db = _get_db()
        try:
            from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyIdempotencyRepository
            idem_repo = SQLAlchemyIdempotencyRepository(db)
            idem_repo.record(key)
        finally:
            db.close()


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
# AUTH ENDPOINTS (shared by both legacy and v1)
# ═══════════════════════════════════════════════════════════

def _driver_to_dict(d) -> Dict[str, Any]:
    """Convert Driver domain object or dict to flat dict for login lookup."""
    if isinstance(d, dict):
        return d
    # Driver domain object — use to_dict() or attributes
    if hasattr(d, 'to_dict'):
        return d.to_dict()
    return {
        "id": getattr(d, 'id', ''),
        "name": getattr(d, 'name', ''),
        "phone": getattr(d, 'phone', ''),
        "tenant_id": getattr(d, 'tenant_id', 'default'),
        "status": getattr(d, 'status', None),
        "active": getattr(d, 'active', True),
    }


def _get_db_session():
    """Get a fresh SQLAlchemy session for driver lookup."""
    from sqlalchemy.orm import Session as DBSession
    from app.infrastructure.database.init_db import engine
    return DBSession(bind=engine)


async def handle_driver_login(req: DriverLoginRequest) -> DriverLoginResponse:
    """Driver app login. Returns session token.
    
    Auth flow:
    1. Find driver by username in database (delivery_drivers table)
    2. Verify password hash
    3. Create session token in memory
    4. Return token
    """
    db = _get_db_session()
    try:
        from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository
        repo = SQLAlchemyDeliveryDriverRepository(db, tenant_id="default")
        
        # Find driver by username
        model = repo.find_by_username(req.username)
        if not model:
            raise HTTPException(401, detail="Invalid credentials")
        
        # Verify password
        if model.password_hash:
            if not bcrypt.checkpw(req.password.encode(), model.password_hash.encode()):
                raise HTTPException(401, detail="Invalid credentials")
        
        # Determine tenant
        tenant_id = model.tenant_id or "default"
        
        # Create session
        token = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(hours=8)
        
        # Persist session to database
        db_session = _get_db()
        try:
            from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDriverSessionRepository
            session_repo = SQLAlchemyDriverSessionRepository(db_session)
            session_repo.create_session(
                token=token,
                driver_id=model.codigo,
                tenant_id=tenant_id,
                role="DRIVER",
                device_id=req.device_id,
                device_name=req.device_name,
                platform=req.platform,
                expires_at=datetime.utcnow() + timedelta(hours=8),
            )
        finally:
            db_session.close()

        return DriverLoginResponse(
            success=True,
            token=token,
            driver_id=model.codigo,
            tenant_id=tenant_id,
            expires_at=expires_at.isoformat(),
        )
    finally:
        db.close()


async def handle_driver_logout(ctx: Dict) -> Dict[str, Any]:
    """Revoke session. Database is the single source of truth."""
    db = _get_db()
    try:
        from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDriverSessionRepository
        session_repo = SQLAlchemyDriverSessionRepository(db)
        session_repo.revoke_session(ctx.get("token", ""))
    finally:
        db.close()
    return {"success": True}


async def handle_driver_me(ctx: Dict) -> DriverMeResponse:
    """Get driver profile from database.

    Database is the single source of truth. No in-memory fallback.
    """
    db = _get_db_session()
    try:
        from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository
        repo = SQLAlchemyDeliveryDriverRepository(db, tenant_id=ctx.get("tenant_id", "default"))
        model = repo.find_by_id_as_model(ctx["driver_id"])
        if not model:
            raise HTTPException(404, detail="Driver not found")
        return DriverMeResponse(
            driver_id=model.codigo,
            name=model.nome,
            phone=model.telefone,
            status=model.status or "AVAILABLE",
            active=model.ativo,
            tenant_id=model.tenant_id or "default",
        )
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# DELIVERY ENDPOINTS (shared)
# ═══════════════════════════════════════════════════════════

async def handle_list_deliveries(
    ctx: Dict, status: Optional[str] = None, limit: int = 20, offset: int = 0,
):
    """List deliveries assigned to THIS driver only."""
    driver_id = ctx["driver_id"]
    tenant_id = ctx["tenant_id"]

    db = _get_db_session()
    try:
        from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository
        repo = SQLAlchemyDeliveryPersistenceRepository(db, tenant_id)
        records = repo.list_deliveries(status=status, driver_id=driver_id, limit=limit, offset=offset)

        summaries = []
        for r in records:
            addr_str = f"{r.address_street}, {r.address_number}"
            if r.address_neighborhood:
                addr_str += f" - {r.address_neighborhood}"
            summaries.append(DriverDeliverySummary(
                delivery_id=r.delivery_id,
                order_reference=r.order_id,
                customer_name=r.customer_name,
                address=addr_str,
                status=r.status,
                scheduled_at=r.scheduled_at.isoformat() if r.scheduled_at else None,
                version=r.version,
            ))
        return {"deliveries": summaries, "count": len(summaries)}
    finally:
        db.close()


async def handle_get_delivery(ctx: Dict, delivery_id: str) -> DriverDeliveryDetail:
    """Get delivery detail for THIS driver only."""
    db = _get_db_session()
    try:
        from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository
        repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx["tenant_id"])
        record = repo.get_delivery(delivery_id)
        if not record:
            raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
        if record.driver_id != ctx["driver_id"]:
            raise HTTPException(404, detail="DELIVERY_NOT_FOUND")

        addr_str = f"{record.address_street}, {record.address_number}"
        if record.address_complement:
            addr_str += f" {record.address_complement}"
        if record.address_neighborhood:
            addr_str += f" - {record.address_neighborhood}"
        if record.address_city:
            addr_str += f", {record.address_city}"

        actions = _allowed_actions(record.status)

        return DriverDeliveryDetail(
            delivery_id=record.delivery_id,
            order_reference=record.order_id,
            customer_name=record.customer_name,
            address=addr_str,
            address_reference=record.address_reference,
            status=record.status,
            scheduled_at=record.scheduled_at.isoformat() if record.scheduled_at else None,
            route_id=record.route_id,
            notes=record.notes,
            version=record.version,
            can_accept=actions["can_accept"],
            can_start=actions["can_start"],
            can_arrive=actions["can_arrive"],
            can_complete=actions["can_complete"],
            can_fail=actions["can_fail"],
        )
    finally:
        db.close()


async def handle_accept_delivery(ctx: Dict, delivery_id: str, req: ActionRequest) -> Dict:
    replay = _check_idempotency(req.idempotency_key)
    if replay:
        return replay

    db = _get_db_session()
    try:
        from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository
        repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx["tenant_id"])
        record = repo.get_delivery(delivery_id)
        if not record:
            raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
        if record.driver_id != ctx["driver_id"]:
            raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
        if record.status != "PENDING":
            raise HTTPException(400, detail=f"INVALID_STATE: current={record.status}, cannot accept")

        record = repo.assign_delivery(delivery_id, ctx["driver_id"], record.vehicle_id, record.version)
        if not record:
            raise HTTPException(409, detail="VERSION_CONFLICT")

        _record_idempotency(req.idempotency_key)
        publish_delivery_event(
            EventType.DELIVERY_ACCEPTED, delivery_id, ctx["tenant_id"],
            driver_id=ctx["driver_id"], data={"previous_status": "PENDING"}
        )
        return {"success": True, "version": record.version}
    finally:
        db.close()


async def handle_start_delivery(ctx: Dict, delivery_id: str, req: ActionRequest) -> Dict:
    replay = _check_idempotency(req.idempotency_key)
    if replay:
        return replay

    db = _get_db_session()
    try:
        from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository
        repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx["tenant_id"])
        record = repo.get_delivery(delivery_id)
        if not record:
            raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
        if record.driver_id != ctx["driver_id"]:
            raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
        if record.status not in ("ASSIGNED", "DISPATCHED"):
            raise HTTPException(400, detail=f"INVALID_STATE: current={record.status}, cannot start")

        record = repo.start_delivery(delivery_id, record.version, ctx["driver_id"])
        if not record:
            raise HTTPException(409, detail="VERSION_CONFLICT")

        _record_idempotency(req.idempotency_key)
        publish_delivery_event(
            EventType.DELIVERY_STARTED, delivery_id, ctx["tenant_id"],
            driver_id=ctx["driver_id"], data={"previous_status": "ASSIGNED"}
        )
        return {"success": True, "version": record.version}
    finally:
        db.close()


async def handle_arrive_delivery(ctx: Dict, delivery_id: str, req: ActionRequest) -> Dict:
    replay = _check_idempotency(req.idempotency_key)
    if replay:
        return replay

    db = _get_db_session()
    try:
        from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository
        repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx["tenant_id"])
        record = repo.get_delivery(delivery_id)
        if not record:
            raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
        if record.driver_id != ctx["driver_id"]:
            raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
        if record.status != "EN_ROUTE":
            raise HTTPException(400, detail=f"INVALID_STATE: current={record.status}, cannot arrive")

        record = repo.arrive_delivery(delivery_id, record.version)
        if not record:
            raise HTTPException(409, detail="VERSION_CONFLICT")

        _record_idempotency(req.idempotency_key)
        publish_delivery_event(
            EventType.DELIVERY_ARRIVED, delivery_id, ctx["tenant_id"],
            driver_id=ctx["driver_id"], data={"previous_status": "EN_ROUTE"}
        )
        return {"success": True, "version": record.version}
    finally:
        db.close()


async def handle_complete_delivery(ctx: Dict, delivery_id: str, req: ActionRequest) -> Dict:
    replay = _check_idempotency(req.idempotency_key)
    if replay:
        return replay

    db = _get_db_session()
    try:
        from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository
        repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx["tenant_id"])
        record = repo.get_delivery(delivery_id)
        if not record:
            raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
        if record.driver_id != ctx["driver_id"]:
            raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
        if record.status != "ARRIVED":
            raise HTTPException(400, detail=f"INVALID_STATE: current={record.status}, cannot complete")

        proof_data = None
        if req.proof_type:
            proof_data = {
                "type": req.proof_type,
                "driver_id": ctx["driver_id"],
            }

        record = repo.complete_delivery(
            delivery_id, record.version,
            proof_type=req.proof_type,
            proof_data=proof_data,
            driver_notes=req.notes or "",
        )
        if not record:
            raise HTTPException(409, detail="VERSION_CONFLICT")

        _record_idempotency(req.idempotency_key)
        publish_delivery_event(
            EventType.DELIVERY_COMPLETED, delivery_id, ctx["tenant_id"],
            driver_id=ctx["driver_id"], data={
                "previous_status": "ARRIVED",
                "proof_type": req.proof_type or None,
            }
        )
        return {"success": True, "version": record.version}
    finally:
        db.close()


async def handle_fail_delivery(ctx: Dict, delivery_id: str, req: ActionRequest) -> Dict:
    replay = _check_idempotency(req.idempotency_key)
    if replay:
        return replay

    db = _get_db_session()
    try:
        from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository
        repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx["tenant_id"])
        record = repo.get_delivery(delivery_id)
        if not record:
            raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
        if record.driver_id != ctx["driver_id"]:
            raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
        if record.status not in ("EN_ROUTE", "ARRIVED"):
            raise HTTPException(400, detail=f"INVALID_STATE: current={record.status}, cannot fail")

        notes = (req.failure_notes or "").replace("<", "").replace(">", "")
        record = repo.fail_delivery(
            delivery_id, record.version,
            reason=req.failure_reason or "OTHER",
            notes=notes,
        )
        if not record:
            raise HTTPException(409, detail="VERSION_CONFLICT")

        _record_idempotency(req.idempotency_key)
        publish_delivery_event(
            EventType.DELIVERY_FAILED, delivery_id, ctx["tenant_id"],
            driver_id=ctx["driver_id"], data={
                "previous_status": "EN_ROUTE",
                "failure_reason": req.failure_reason or "OTHER",
                "failure_notes": notes,
            }
        )
        return {"success": True, "version": record.version}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# ROUTE ENDPOINTS (shared)
# Category A — transient operational state (route plan for dispatch session).
# Routes are computed by dispatch and consumed within the same operational cycle.
# TODO Fase 21: persist routes when multi-stop route planning requires restart survival.
# ═══════════════════════════════════════════════════════════

async def handle_list_routes(ctx: Dict) -> Dict:
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


async def handle_current_route(ctx: Dict) -> DriverRouteDetail:
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
# LOCATION ENDPOINT (shared)
# ═══════════════════════════════════════════════════════════

async def handle_update_location(ctx: Dict, req: LocationUpdate) -> Dict:
    driver_id = ctx["driver_id"]
    tenant_id = ctx["tenant_id"]

    db = _get_db_session()
    try:
        from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDriverLocationRepository
        loc_repo = SQLAlchemyDriverLocationRepository(db)

        # Rate limit: skip if last update was < 10s ago
        existing = loc_repo.get_location(tenant_id, driver_id)
        if existing:
            age = (datetime.utcnow() - existing.timestamp).total_seconds()
            if age < 10:
                return {"success": True, "throttled": True}

        loc_repo.upsert_location(
            tenant_id=tenant_id,
            driver_id=driver_id,
            latitude=req.latitude,
            longitude=req.longitude,
            accuracy=req.accuracy,
            speed=req.speed,
            bearing=req.bearing,
        )

        publish_driver_event(
            EventType.DRIVER_LOCATION_UPDATED, driver_id, tenant_id,
            data={
                "latitude": req.latitude,
                "longitude": req.longitude,
                "accuracy": req.accuracy,
                "speed": req.speed,
                "bearing": req.bearing,
            }
        )
        return {"success": True}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# AVAILABILITY ENDPOINT (shared)
# ═══════════════════════════════════════════════════════════

class AvailabilityRequest(BaseModel):
    status: str = Field(..., pattern="^(AVAILABLE|PAUSED|UNAVAILABLE)$")
    reason: Optional[str] = None


async def handle_set_availability(ctx: Dict, req: AvailabilityRequest) -> Dict:
    """Driver toggles availability. Persists to database."""
    db = _get_db_session()
    try:
        from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository
        repo = SQLAlchemyDeliveryDriverRepository(db, tenant_id=ctx["tenant_id"])
        model = repo.find_by_id_as_model(ctx["driver_id"])
        if not model:
            raise HTTPException(404, detail="Driver not found")
        model.status = req.status
        db.commit()
        publish_driver_event(
            EventType.DRIVER_AVAILABLE if req.status == "AVAILABLE" else EventType.DRIVER_PAUSED,
            ctx["driver_id"], ctx["tenant_id"],
            data={"new_status": req.status, "reason": req.reason or ""}
        )
        return {"success": True, "status": model.status}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# PROOF ENDPOINT (shared)
# ═══════════════════════════════════════════════════════════

async def handle_upload_proof(ctx: Dict, delivery_id: str, proof_type: str, notes: str = "") -> Dict:
    """Upload delivery proof. Uses database as single source of truth."""
    valid_types = {"PHOTO", "SIGNATURE", "OTP", "MANUAL_CONFIRMATION"}
    if proof_type not in valid_types:
        raise HTTPException(400, detail=f"PROOF_INVALID: type={proof_type}")

    db = _get_db_session()
    try:
        from app.infrastructure.repositories.delivery_persistence_repository import SQLAlchemyDeliveryPersistenceRepository
        repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx["tenant_id"])
        record = repo.get_delivery(delivery_id)
        if not record:
            raise HTTPException(404, detail="DELIVERY_NOT_FOUND")
        if record.driver_id != ctx["driver_id"]:
            raise HTTPException(403, detail="FORBIDDEN")

        proof_id = str(uuid.uuid4())
        record.proof_type = proof_type
        record.proof_data = {
            "proof_id": proof_id,
            "driver_id": ctx["driver_id"],
            "notes": notes,
            "created_at": datetime.utcnow().isoformat(),
        }
        db.commit()
        return {"success": True, "proof_id": proof_id}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# SYNC ENDPOINT (shared)
# ═══════════════════════════════════════════════════════════

async def handle_sync(ctx: Dict, req: SyncRequest) -> SyncResponse:
    """Offline sync. Uses database as single source of truth."""
    driver_id = ctx["driver_id"]
    tenant_id = ctx["tenant_id"]

    accepted = []
    rejected = []
    conflicts = []

    db = _get_db_session()
    try:
        from app.infrastructure.repositories.delivery_persistence_repository import (
            SQLAlchemyDeliveryPersistenceRepository, SQLAlchemyIdempotencyRepository
        )
        delivery_repo = SQLAlchemyDeliveryPersistenceRepository(db, tenant_id)
        idem_repo = SQLAlchemyIdempotencyRepository(db)

        for action in req.actions:
            action_type = action.get("type", "")
            delivery_id = action.get("delivery_id", "")
            idempotency_key = action.get("idempotency_key")
            client_version = action.get("client_version", 0)

            if idempotency_key and idem_repo.exists(idempotency_key):
                accepted.append(idempotency_key)
                continue

            record = delivery_repo.get_delivery(delivery_id)
            if not record:
                rejected.append({"action": action_type, "delivery_id": delivery_id,
                                 "error": "DELIVERY_NOT_FOUND"})
                continue
            if record.driver_id != driver_id:
                rejected.append({"action": action_type, "delivery_id": delivery_id,
                                 "error": "FORBIDDEN"})
                continue

            server_version = record.version
            if client_version and client_version < server_version:
                conflicts.append({
                    "action": action_type,
                    "delivery_id": delivery_id,
                    "current_version": server_version,
                    "current_status": record.status,
                    "client_version": client_version,
                })
                continue

            result_record = None
            previous_status = record.status
            if action_type == "start" and record.status in ("ASSIGNED", "DISPATCHED"):
                result_record = delivery_repo.start_delivery(delivery_id, server_version, driver_id)
            elif action_type == "arrive" and record.status == "EN_ROUTE":
                result_record = delivery_repo.arrive_delivery(delivery_id, server_version)
            elif action_type == "complete" and record.status == "ARRIVED":
                result_record = delivery_repo.complete_delivery(delivery_id, server_version)
            elif action_type == "fail" and record.status in ("EN_ROUTE", "ARRIVED"):
                result_record = delivery_repo.fail_delivery(
                    delivery_id, server_version,
                    reason=action.get("failure_reason", "OTHER"),
                    notes=(action.get("failure_notes", "") or "").replace("<", "").replace(">", ""),
                )

            if result_record:
                if idempotency_key:
                    idem_repo.record(idempotency_key)
                accepted.append(idempotency_key or action_type)
                _sync_event_map = {
                    "start": EventType.DELIVERY_STARTED,
                    "arrive": EventType.DELIVERY_ARRIVED,
                    "complete": EventType.DELIVERY_COMPLETED,
                    "fail": EventType.DELIVERY_FAILED,
                }
                if action_type in _sync_event_map:
                    publish_delivery_event(
                        _sync_event_map[action_type], delivery_id, tenant_id,
                        driver_id=driver_id, data={"source": "sync"}
                    )
            else:
                rejected.append({"action": action_type, "delivery_id": delivery_id,
                                 "error": f"INVALID_STATE: {record.status}"})
    finally:
        db.close()

    return SyncResponse(
        accepted=accepted,
        rejected=rejected,
        conflicts=conflicts,
        next_sync_token=str(uuid.uuid4()),
    )


# ═══════════════════════════════════════════════════════════
# LEGACY ROUTER (backward compatibility: /api/driver/v1/*)
# ═══════════════════════════════════════════════════════════

router = APIRouter(prefix="/api/driver", tags=["driver-app-legacy"])


@router.post("/v1/auth/login", response_model=DriverLoginResponse)
async def legacy_driver_login(req: DriverLoginRequest):
    """[LEGACY] Driver app login. Use /api/v1/driver/auth/login instead."""
    return await handle_driver_login(req)


@router.post("/v1/auth/logout")
async def legacy_driver_logout(ctx: Dict = Depends(_authenticate_driver)):
    """[LEGACY] Driver app logout."""
    return await handle_driver_logout(ctx)


@router.get("/v1/me", response_model=DriverMeResponse)
async def legacy_driver_me(ctx: Dict = Depends(_authenticate_driver)):
    """[LEGACY] Get driver profile."""
    return await handle_driver_me(ctx)


@router.get("/v1/deliveries")
async def legacy_list_deliveries(
    status: Optional[str] = None, limit: int = 20, offset: int = 0,
    ctx: Dict = Depends(_authenticate_driver),
):
    """[LEGACY] List deliveries."""
    return await handle_list_deliveries(ctx, status=status, limit=limit, offset=offset)


@router.get("/v1/deliveries/{delivery_id}", response_model=DriverDeliveryDetail)
async def legacy_get_delivery(delivery_id: str, ctx: Dict = Depends(_authenticate_driver)):
    """[LEGACY] Get delivery detail."""
    return await handle_get_delivery(ctx, delivery_id)


@router.post("/v1/deliveries/{delivery_id}/accept")
async def legacy_accept_delivery(delivery_id: str, req: ActionRequest = ActionRequest(),
                                  ctx: Dict = Depends(_authenticate_driver)):
    """[LEGACY] Accept delivery."""
    return await handle_accept_delivery(ctx, delivery_id, req)


@router.post("/v1/deliveries/{delivery_id}/start")
async def legacy_start_delivery(delivery_id: str, req: ActionRequest = ActionRequest(),
                                 ctx: Dict = Depends(_authenticate_driver)):
    """[LEGACY] Start route."""
    return await handle_start_delivery(ctx, delivery_id, req)


@router.post("/v1/deliveries/{delivery_id}/arrive")
async def legacy_arrive_delivery(delivery_id: str, req: ActionRequest = ActionRequest(),
                                  ctx: Dict = Depends(_authenticate_driver)):
    """[LEGACY] Arrive at location."""
    return await handle_arrive_delivery(ctx, delivery_id, req)


@router.post("/v1/deliveries/{delivery_id}/complete")
async def legacy_complete_delivery(delivery_id: str, req: ActionRequest = ActionRequest(),
                                    ctx: Dict = Depends(_authenticate_driver)):
    """[LEGACY] Complete delivery."""
    return await handle_complete_delivery(ctx, delivery_id, req)


@router.post("/v1/deliveries/{delivery_id}/fail")
async def legacy_fail_delivery(delivery_id: str, req: ActionRequest,
                                ctx: Dict = Depends(_authenticate_driver)):
    """[LEGACY] Report failure."""
    return await handle_fail_delivery(ctx, delivery_id, req)


@router.get("/v1/routes")
async def legacy_list_routes(ctx: Dict = Depends(_authenticate_driver)):
    """[LEGACY] List routes."""
    return await handle_list_routes(ctx)


@router.get("/v1/routes/current")
async def legacy_current_route(ctx: Dict = Depends(_authenticate_driver)):
    """[LEGACY] Current active route."""
    return await handle_current_route(ctx)


@router.post("/v1/location")
async def legacy_update_location(req: LocationUpdate, ctx: Dict = Depends(_authenticate_driver)):
    """[LEGACY] Update GPS location."""
    return await handle_update_location(ctx, req)


@router.post("/v1/proofs")
async def legacy_upload_proof(
    delivery_id: str = Header(...), proof_type: str = Header(...),
    notes: str = Header(default=""), ctx: Dict = Depends(_authenticate_driver),
):
    """[LEGACY] Upload delivery proof."""
    return await handle_upload_proof(ctx, delivery_id, proof_type, notes)


@router.post("/v1/sync")
async def legacy_sync(req: SyncRequest, ctx: Dict = Depends(_authenticate_driver)):
    """[LEGACY] Offline sync."""
    return await handle_sync(ctx, req)
