"""
Auth Middleware — FASE 13

FastAPI dependency for authentication and authorization.
"""

from typing import Optional
from fastapi import Header, HTTPException
from app.application.security.auth_service import AuthService
from app.domain.security.models import TenantContext


def create_auth_dependency(auth_service: AuthService):
    """Create an auth dependency for FastAPI."""

    def require_auth(authorization: Optional[str] = Header(None)) -> TenantContext:
        token = ""
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
        ctx = auth_service.validate_token(token)
        if not ctx:
            raise HTTPException(status_code=401, detail="Authentication required")
        return ctx

    def require_admin(authorization: Optional[str] = Header(None)) -> TenantContext:
        ctx = require_auth(authorization)
        if ctx.role.value not in ("ADMIN", "SYSTEM"):
            raise HTTPException(status_code=403, detail="Admin access required")
        return ctx

    def require_permission(permission: str):
        def checker(authorization: Optional[str] = Header(None)) -> TenantContext:
            ctx = require_auth(authorization)
            if not ctx.has_permission(permission):
                raise HTTPException(status_code=403, detail=f"Permission '{permission}' required")
            return ctx
        return checker

    return require_auth, require_admin, require_permission
