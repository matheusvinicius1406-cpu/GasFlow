"""Admin API — P0 3.3 (RBAC persistido + auditoria).

Todos os endpoints exigem permissão explícita via require_permission —
sem exceção. Mutações gravam auth_audit_log com before_json/after_json
(snapshot SEM segredos — senha nunca entra em log). Mutação de
role/permissão invalida o cache do PermissionPolicyLoader
(evento `permissions.changed`).

Nota: /auth (auth.py) mantém os endpoints legados (require_admin); este
router é a superfície fine-grained do admin console (3.4/3.5).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.application.security.permission_policy_loader import get_policy_loader
from app.domain.security.models import TenantContext
from app.infrastructure.database.init_db import engine
from app.infrastructure.repositories.auth_model import AuthRoleModel, AuthUserModel
from app.presentation.dependencies import require_permission

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Helpers ─────────────────────────────────────────────


def _session():
    from sqlalchemy.orm import Session as DBSession

    return DBSession(bind=engine)


def _audit_mutation(
    ctx: TenantContext,
    action: str,
    resource: str,
    resource_id: str,
    before: Optional[dict],
    after: Optional[dict],
) -> None:
    """Grava mutação sensível em auth_audit_log com before/after.

    Snapshot SEM segredos: password_hash e password são sempre removidos.
    """

    from app.infrastructure.repositories.auth_repository import SQLAlchemyAuditRepository

    def _clean(snapshot: Optional[dict]) -> Optional[dict]:
        if snapshot is None:
            return None
        return {k: v for k, v in snapshot.items() if k not in ("password", "password_hash")}

    db = _session()
    try:
        SQLAlchemyAuditRepository(db).create(
            actor_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            before_json=_clean(before),
            after_json=_clean(after),
            platform="desktop",
        )
    finally:
        db.close()


def _user_snapshot(user: AuthUserModel) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "status": user.status,
        "role_id": user.role_id,
        "must_change_password": bool(user.must_change_password),
    }


def _generate_temp_password() -> str:
    """Senha temporária legível para ditado: 3 grupos de 4 (A-Z, 2-9 sem ambíguos)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    groups = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3)]
    return "-".join(groups)


def _resolve_role(db, role_id: Optional[str], role_name: Optional[str]):
    if role_id:
        return db.query(AuthRoleModel).filter(AuthRoleModel.id == role_id).first()
    if role_name:
        return db.query(AuthRoleModel).filter(AuthRoleModel.name == role_name).first()
    return None


# ── Schemas ─────────────────────────────────────────────


class CreateUserBody(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: str = Field(..., min_length=5, max_length=200)
    password: str = Field(..., min_length=6, max_length=200)
    display_name: str = ""
    role_id: Optional[str] = None
    role: Optional[str] = None  # nome do role (ex.: "OPERATOR") — atalho


class UpdateUserBody(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    email: Optional[str] = Field(None, min_length=5, max_length=200)
    display_name: Optional[str] = Field(None, max_length=200)
    role_id: Optional[str] = None


class ResetPasswordResponse(BaseModel):
    success: bool
    temporary_password: str
    must_change_password: bool


class UpdateRolePermissionsBody(BaseModel):
    permissions: List[str] = Field(..., description="Lista completa de permissões do role")


# ── Users ───────────────────────────────────────────────


@router.get("/users")
async def list_users(
    ctx: TenantContext = Depends(require_permission("user.read")),
    search: Optional[str] = None,
    role_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
):
    db = _session()
    try:
        query = db.query(AuthUserModel)
        if search:
            like = f"%{search}%"
            query = query.filter(
                AuthUserModel.username.ilike(like)
                | AuthUserModel.email.ilike(like)
                | AuthUserModel.display_name.ilike(like)
            )
        if role_id:
            query = query.filter(AuthUserModel.role_id == role_id)
        if status:
            query = query.filter(AuthUserModel.status == status)
        users = query.limit(limit).all()
        return {
            "users": [
                {
                    "id": u.id,
                    "username": u.username,
                    "email": u.email,
                    "display_name": u.display_name,
                    "status": u.status,
                    "role_id": u.role_id,
                    "must_change_password": bool(u.must_change_password),
                    "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                }
                for u in users
            ]
        }
    finally:
        db.close()


@router.post("/users", status_code=201)
async def create_user(
    body: CreateUserBody,
    ctx: TenantContext = Depends(require_permission("user.create")),
):
    from app.domain.security.models import hash_password

    db = _session()
    try:
        if db.query(AuthUserModel).filter(AuthUserModel.username == body.username).first():
            raise HTTPException(status_code=400, detail="Username already exists")

        role = _resolve_role(db, body.role_id, body.role)
        if role is None:
            raise HTTPException(status_code=400, detail="Role not found")

        user = AuthUserModel(
            id=str(uuid.uuid4()),
            username=body.username,
            email=body.email,
            display_name=body.display_name or body.username,
            password_hash=hash_password(body.password),
            status="ACTIVE",
            role_id=role.id,
            must_change_password=True,
            created_by=ctx.user_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        _audit_mutation(ctx, "USER_CREATED", "user", user.id, None, _user_snapshot(user))
        return {"success": True, "user_id": user.id}
    finally:
        db.close()


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserBody,
    ctx: TenantContext = Depends(require_permission("user.update")),
):
    db = _session()
    try:
        user = db.query(AuthUserModel).filter(AuthUserModel.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        before = _user_snapshot(user)

        if body.role_id is not None:
            role = db.query(AuthRoleModel).filter(AuthRoleModel.id == body.role_id).first()
            if not role:
                raise HTTPException(status_code=400, detail="Role not found")
        for field in ("username", "email", "display_name", "role_id"):
            value = getattr(body, field)
            if value is not None:
                setattr(user, field, value)
        user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user)

        _audit_mutation(ctx, "RESOURCE_MODIFIED", "user", user.id, before, _user_snapshot(user))
        return {"success": True, "user": _user_snapshot(user)}
    finally:
        db.close()


@router.post("/users/{user_id}/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    user_id: str,
    ctx: TenantContext = Depends(require_permission("user.reset_password")),
):
    """Gera senha temporária (bcrypt), força troca no próximo login.

    A senha volta ao caller UMA vez e nunca vai para log/audit.
    """
    from app.domain.security.models import hash_password

    db = _session()
    try:
        user = db.query(AuthUserModel).filter(AuthUserModel.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        before = _user_snapshot(user)

        temp_password = _generate_temp_password()
        user.password_hash = hash_password(temp_password)
        user.must_change_password = True
        user.updated_at = datetime.utcnow()
        db.commit()

        _audit_mutation(
            ctx,
            "PASSWORD_CHANGED",
            "user",
            user.id,
            before,
            {"must_change_password": True, "reset_by": ctx.user_id},
        )
        return ResetPasswordResponse(success=True, temporary_password=temp_password, must_change_password=True)
    finally:
        db.close()


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    ctx: TenantContext = Depends(require_permission("user.deactivate")),
):
    """Soft delete: status=DISABLED (preserva histórico e auditoria)."""
    db = _session()
    try:
        user = db.query(AuthUserModel).filter(AuthUserModel.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user.id == ctx.user_id:
            raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
        before = _user_snapshot(user)

        user.status = "DISABLED"
        user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user)

        _audit_mutation(ctx, "USER_DISABLED", "user", user.id, before, _user_snapshot(user))
        return {"success": True, "user": _user_snapshot(user)}
    finally:
        db.close()


@router.post("/users/{user_id}/activate")
async def activate_user(
    user_id: str,
    ctx: TenantContext = Depends(require_permission("user.deactivate")),
):
    db = _session()
    try:
        user = db.query(AuthUserModel).filter(AuthUserModel.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        before = _user_snapshot(user)

        user.status = "ACTIVE"
        user.failed_login_attempts = 0
        user.locked_until = None
        user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user)

        _audit_mutation(ctx, "RESOURCE_MODIFIED", "user", user.id, before, _user_snapshot(user))
        return {"success": True, "user": _user_snapshot(user)}
    finally:
        db.close()


# ── Roles ───────────────────────────────────────────────


@router.get("/roles")
async def list_roles(ctx: TenantContext = Depends(require_permission("role.manage"))):
    db = _session()
    try:
        roles = db.query(AuthRoleModel).order_by(AuthRoleModel.name).all()
        return {
            "roles": [
                {
                    "id": r.id,
                    "name": r.name,
                    "system_role": r.system_role,
                    "permissions": r.permissions or [],
                }
                for r in roles
            ]
        }
    finally:
        db.close()


@router.patch("/roles/{role_id}/permissions")
async def update_role_permissions(
    role_id: str,
    body: UpdateRolePermissionsBody,
    ctx: TenantContext = Depends(require_permission("permission.assign")),
):
    """Atualiza a matriz role→permissões (JSON do auth_roles) e a normalizada.

    Invalida o cache do PermissionPolicyLoader (permissions.changed).
    """
    from sqlalchemy import text

    db = _session()
    try:
        role = db.query(AuthRoleModel).filter(AuthRoleModel.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        before = {"name": role.name, "permissions": list(role.permissions or [])}

        # Valida códigos contra o catálogo (desconhecido = 400).
        id_by_code = {row.code: row.id for row in db.execute(text("SELECT id, code FROM permissions")).fetchall()}
        unknown = [c for c in body.permissions if c not in id_by_code]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown permissions: {unknown}")

        # 1. JSON legacy (fonte do loader quando matriz vazia).
        role.permissions = sorted(set(body.permissions))
        # 2. Matriz normalizada (fonte primária do loader).
        db.execute(text("DELETE FROM role_permissions WHERE role_id = :rid"), {"rid": role_id})
        for code in sorted(set(body.permissions)):
            db.execute(
                text("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (:rid, :pid)"),
                {"rid": role_id, "pid": id_by_code[code]},
            )
        db.commit()

        # permissions.changed: cache de 60s não pode servir dados velhos.
        get_policy_loader().invalidate_all()

        _audit_mutation(
            ctx,
            "ROLE_CHANGED",
            "role",
            role_id,
            before,
            {"name": role.name, "permissions": role.permissions},
        )
        return {"success": True, "role": {"id": role.id, "name": role.name, "permissions": role.permissions}}
    finally:
        db.close()


# ── Audit ───────────────────────────────────────────────


@router.get("/audit")
async def list_audit(
    ctx: TenantContext = Depends(require_permission("audit.view")),
    actor_id: Optional[str] = None,
    action: Optional[str] = None,
    resource: Optional[str] = None,
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    db = _session()
    try:
        from app.infrastructure.repositories.auth_repository import SQLAlchemyAuditRepository

        rows = SQLAlchemyAuditRepository(db).list_filtered(
            tenant_id=ctx.tenant_id,
            actor_id=actor_id,
            action=action,
            resource=resource,
            from_ts=from_ts,
            to_ts=to_ts,
            offset=offset,
            limit=limit,
        )
        return {
            "records": [
                {
                    "id": r.id,
                    "actor_id": r.actor_id,
                    "action": r.action,
                    "resource": r.resource,
                    "resource_id": r.resource_id,
                    "result": r.result,
                    "timestamp": r.timestamp.isoformat(),
                    "before_json": r.before_json,
                    "after_json": r.after_json,
                    "platform": r.platform,
                }
                for r in rows
            ]
        }
    finally:
        db.close()
