"""
Shared Dependencies — Authentication, Authorization, Tenant Context.

All protected routers should import and use these dependencies.

Usage in router:
    from app.presentation.dependencies import get_tenant_context, require_admin

    @router.get("/items")
    def list_items(ctx: TenantContext = Depends(get_tenant_context)):
        ...

    @router.get("/admin/items")
    def admin_items(ctx: TenantContext = Depends(require_admin)):
        ...
"""

import hmac
from typing import Optional

from fastapi import Depends, Header, HTTPException

from app.application.security.auth_service import AuthService
from app.domain.security.models import TenantContext, SystemRole


# ── Singleton Auth Service ──────────────────────────────

_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        from sqlalchemy.orm import Session as DBSession
        from app.infrastructure.database.init_db import engine

        db = DBSession(bind=engine)
        _auth_service = AuthService(db=db)
    return _auth_service


# ── Core Dependency: Tenant Context ─────────────────────


def get_tenant_context(authorization: Optional[str] = Header(None)) -> TenantContext:
    """Extract and validate tenant context from Authorization header.

    Used by all protected endpoints.
    Returns TenantContext with user_id, tenant_id, role, permissions.
    Raises 401 if token is missing, invalid, or expired.
    """
    auth = get_auth_service()
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    ctx = auth.validate_token(token)
    if not ctx:
        raise HTTPException(status_code=401, detail="Authentication required")
    return ctx


# ── Admin-only Dependency ───────────────────────────────


def require_admin(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    """Require admin role. Raises 403 if not admin."""
    if ctx.role != SystemRole.ADMIN and not ctx.has_permission("admin.*"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return ctx


# ── Role-based Dependency Factory ───────────────────────


def require_role(*allowed_roles: SystemRole):
    """Dependency factory: require one of the specified roles.

    Usage:
        @router.get("/items")
        def list_items(ctx: TenantContext = Depends(require_role(SystemRole.ADMIN, SystemRole.MANAGER))):
            ...
    """

    def _check(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if ctx.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return ctx

    return _check


# ── Permission-based Dependency Factory ─────────────────


def require_permission(permission: str):
    """Dependency factory: require a specific permission.

    Usage:
        @router.post("/items")
        def create_item(ctx: TenantContext = Depends(require_permission("item.create"))):
            ...
    """

    def _check(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if not ctx.has_permission(permission) and ctx.role != SystemRole.ADMIN:
            raise HTTPException(status_code=403, detail=f"Permission '{permission}' required")
        return ctx

    return _check


# ── Public endpoint marker (no auth needed) ─────────────

# Endpoints that DON'T use get_tenant_context are implicitly public.
# The following are explicitly public by convention:
# - POST /auth/login
# - GET /health
# - GET / (root)
# - WhatsApp proxy (backend → WhatsApp service, authenticated via API key)
# - Driver API (own auth mechanism)


# ── Service-to-Service (whatsapp → backend) ─────────────


def require_whatsapp_service_or_user(
    authorization: Optional[str] = Header(None),
    x_gasflow_key: Optional[str] = Header(None),
) -> TenantContext:
    """Aceita chamada do serviço WhatsApp (X-GasFlow-Key) OU usuário autenticado.

    Usado em endpoints que o serviço WhatsApp precisa chamar (ex.:
    POST /whatsapp/incoming). O serviço autentica com a chave compartilhada
    (WHATSAPP_SERVICE_KEY/MARCOS_GAS_API_KEY); usuários continuam usando Bearer.
    Sem chave configurada no backend, apenas usuários autenticados passam.
    """
    from app.core.config import settings

    service_key = settings.whatsapp_service_key
    if service_key and x_gasflow_key and hmac.compare_digest(service_key, x_gasflow_key):
        return TenantContext(
            user_id="service:whatsapp",
            tenant_id="1",
            role=SystemRole.SYSTEM,
            permissions=set(),
            session_id="service",
        )
    # Fallback: usuário normal (Bearer token)
    return get_tenant_context(authorization)
