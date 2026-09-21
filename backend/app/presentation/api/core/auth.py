"""
Auth API — FASE 13

POST /auth/login — Authenticate (emite access JWT + refresh)
POST /auth/refresh — Rotaciona access+refresh (B5)
POST /auth/logout — Revoke session
GET /auth/me — Current user
GET /auth/users — List users (admin)
POST /auth/users — Create user (admin)
GET /auth/roles — List roles
GET /auth/audit — Audit log (admin)
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field, field_validator
from typing import Optional

from app.domain.security.models import TenantContext
from app.presentation.dependencies import get_auth_service, get_tenant_context, require_admin

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ─────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)
    # B5: a plataforma entra no access token (desktop x mobile). Default desktop
    # para não quebrar cliente que já chama /auth/login sem esse campo.
    platform: str = Field("desktop", max_length=20)


class LoginResponse(BaseModel):
    success: bool
    # `token` segue sendo o token opaco da sessão (compatibilidade); o console
    # usa `access_token` + `refresh_token`.
    token: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    user: Optional[dict] = None
    tenant_id: Optional[str] = None
    role: Optional[str] = None
    expires_at: Optional[str] = None
    error: Optional[str] = None


class RefreshRequest(BaseModel):
    """B5: corpo do refresh é o token opaco emitido no login."""

    refresh_token: str = Field(..., min_length=16, max_length=500)


class RefreshResponse(BaseModel):
    success: bool
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    tenant_id: Optional[str] = None
    role: Optional[str] = None
    error: Optional[str] = None


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: str = Field(..., min_length=5, max_length=200)
    password: str = Field(..., min_length=6, max_length=200)
    display_name: str = ""
    role: str = "OPERATOR"
    tenant_id: Optional[str] = None  # defaults to caller's tenant


class CreateTenantRequest(BaseModel):
    tenant_id: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=200)


class ChangePasswordRequest(BaseModel):
    """P0 (3.8): troca obrigatória/self-service de senha.

    Política mínima (espelha a senha temporária do admin): 8+ chars,
    1 maiúscula, 1 minúscula, 1 dígito.
    """

    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=200)

    @field_validator("new_password")
    @classmethod
    def password_policy(cls, v: str) -> str:
        """8+ chars com maiúscula, minúscula e dígito (lookahead não existe
        no engine de regex do pydantic-core → validação explícita)."""
        if not (any(c.islower() for c in v) and any(c.isupper() for c in v) and any(c.isdigit() for c in v)):
            raise ValueError("password must contain uppercase, lowercase and digit")
        return v


class UserInfo(BaseModel):
    id: str
    username: str
    email: str
    display_name: str
    status: str


class TenantInfo(BaseModel):
    id: str
    name: str


# ── Endpoints ───────────────────────────────────────────


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request):
    auth = get_auth_service()
    result = auth.login(
        req.username,
        req.password,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        platform=req.platform,
    )
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["error"])
    return LoginResponse(**result)


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(req: RefreshRequest, request: Request):
    """B5: troca o refresh por um par novo (rotação com detecção de reuso).

    401 é a resposta para refresh inválido **e** para reuso de refresh já
    rotacionado (a sessão foi revogada no segundo caso) — o cliente deve voltar
    para a tela de login nos dois.
    """
    auth = get_auth_service()
    result = auth.refresh_session(req.refresh_token, ip_address=_client_ip(request))
    if not result:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return RefreshResponse(**result)


@router.post("/logout")
async def logout(request: Request, ctx: TenantContext = Depends(get_tenant_context)):
    """Revoga a sessão do caller (funciona com access JWT ou token opaco).

    Antes isto chamava `revoke()` num modelo ORM que não tem esse método: em
    modo DB o endpoint respondia 500 e a sessão ficava viva. A revogação real é
    pelo repositório, a partir do token que chegou no header.
    """
    auth = get_auth_service()
    token = _bearer_token(request)
    if token and auth.logout(token):
        return {"success": True}
    raise HTTPException(status_code=401, detail="Invalid session")


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


def _client_ip(request: Request) -> str:
    """IP do cliente para a trilha de auditoria (proxy-aware no primeiro hop)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


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
        "must_change_password": bool(getattr(user, "must_change_password", False)),
    }


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest, ctx: TenantContext = Depends(get_tenant_context)):
    """P0 (3.8): troca self-service; exige a senha atual.

    Quando o login expõe must_change_password=true (reset admin), o cliente
    bloqueia o app até esta chamada ter sucesso (limpa a flag no backend).
    """
    auth = get_auth_service()
    result = auth.change_password(ctx.user_id, req.current_password, req.new_password, clear_must_change=True)
    if not result["success"]:
        status = 400 if "incorrect" not in result["error"] else 403
        raise HTTPException(status_code=status, detail=result["error"])
    return {"success": True}


@router.get("/users")
async def list_users(ctx: TenantContext = Depends(require_admin)):
    auth = get_auth_service()
    users = auth.get_users(ctx.tenant_id)
    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "display_name": u.display_name,
                "status": u.status.value,
            }
            for u in users
        ]
    }


@router.post("/users")
async def create_user(req: CreateUserRequest, ctx: TenantContext = Depends(require_admin)):
    auth = get_auth_service()
    result = auth.create_user(
        req.username, req.email, req.password, req.display_name, req.role, req.tenant_id or ctx.tenant_id
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"success": True, "user_id": result["user_id"]}


@router.get("/roles")
async def list_roles(ctx: TenantContext = Depends(get_tenant_context)):
    auth = get_auth_service()
    roles = auth.get_roles()
    return {
        "roles": [
            {"id": r.id, "name": r.name, "system_role": r.system_role.value, "permissions": r.permissions}
            for r in roles
        ]
    }


@router.get("/audit")
async def get_audit(ctx: TenantContext = Depends(require_admin), limit: int = 50):
    auth = get_auth_service()
    records = auth.get_audit_log(ctx.tenant_id, limit)
    return {
        "records": [
            {
                "id": r.id,
                "actor_id": r.actor_id,
                "action": r.action,
                "resource": r.resource,
                "result": r.result,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in records
        ]
    }


@router.get("/tenants")
async def list_tenants(ctx: TenantContext = Depends(require_admin)):
    """List all tenants (admin only)."""
    auth = get_auth_service()
    tenants = auth.get_tenants()
    return {"tenants": [{"id": t.id, "name": t.name} for t in tenants]}


@router.post("/tenants")
async def create_tenant(req: CreateTenantRequest, ctx: TenantContext = Depends(require_admin)):
    """Create a new tenant (admin only)."""
    auth = get_auth_service()
    result = auth.create_tenant(req.tenant_id, req.name, ctx.user_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"success": True, "tenant_id": result["tenant_id"]}
