"""
Auth API — FASE 13

POST /auth/login — Authenticate
POST /auth/logout — Revoke session
GET /auth/me — Current user
GET /auth/users — List users (admin)
POST /auth/users — Create user (admin)
GET /auth/roles — List roles
GET /auth/audit — Audit log (admin)
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Optional, List

from app.domain.security.models import TenantContext, SystemRole
from app.presentation.dependencies import get_auth_service, get_tenant_context, require_admin

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ─────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)

class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    user: Optional[dict] = None
    tenant_id: Optional[str] = None
    role: Optional[str] = None
    expires_at: Optional[str] = None
    error: Optional[str] = None

class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: str = Field(..., min_length=5, max_length=200)
    password: str = Field(..., min_length=6, max_length=200)
    display_name: str = ""
    role: str = "OPERATOR"

class UserInfo(BaseModel):
    id: str
    username: str
    email: str
    display_name: str
    status: str


# ── Endpoints ───────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    auth = get_auth_service()
    result = auth.login(req.username, req.password)
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["error"])
    return LoginResponse(**result)


@router.post("/logout")
async def logout(ctx: TenantContext = Depends(get_tenant_context)):
    auth = get_auth_service()
    # Find and revoke current session
    sessions = auth.get_active_sessions(ctx.user_id)
    for s in sessions:
        if s.tenant_id == ctx.tenant_id:
            s.revoke()
            break
    return {"success": True}


@router.get("/me")
async def get_me(ctx: TenantContext = Depends(get_tenant_context)):
    auth = get_auth_service()
    user = auth.get_user(ctx.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "status": user.status.value,
        "tenant_id": ctx.tenant_id,
        "role": ctx.role.value,
        "permissions": list(ctx.permissions),
    }


@router.get("/users")
async def list_users(ctx: TenantContext = Depends(require_admin)):
    auth = get_auth_service()
    users = auth.get_users(ctx.tenant_id)
    return {"users": [
        {"id": u.id, "username": u.username, "email": u.email,
         "display_name": u.display_name, "status": u.status.value}
        for u in users
    ]}


@router.post("/users")
async def create_user(req: CreateUserRequest, ctx: TenantContext = Depends(require_admin)):
    auth = get_auth_service()
    result = auth.create_user(req.username, req.email, req.password,
                              req.display_name, req.role, ctx.tenant_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"success": True, "user_id": result["user_id"]}


@router.get("/roles")
async def list_roles(ctx: TenantContext = Depends(get_tenant_context)):
    auth = get_auth_service()
    roles = auth.get_roles()
    return {"roles": [
        {"id": r.id, "name": r.name, "system_role": r.system_role.value,
         "permissions": r.permissions}
        for r in roles
    ]}


@router.get("/audit")
async def get_audit(ctx: TenantContext = Depends(require_admin),
                    limit: int = 50):
    auth = get_auth_service()
    records = auth.get_audit_log(ctx.tenant_id, limit)
    return {"records": [
        {"id": r.id, "actor_id": r.actor_id, "action": r.action,
         "resource": r.resource, "result": r.result,
         "timestamp": r.timestamp.isoformat()}
        for r in records
    ]}
