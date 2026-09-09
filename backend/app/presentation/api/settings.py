"""
Settings API — Quadro de Configurações Centralizado + permissões.

Endpoints (todos sob /settings):
    GET  /settings                      — todas as configurações agrupadas  (settings.read)
    GET  /settings/category/{category}  — configurações de uma categoria   (settings.read)
    GET  /settings/key/{key}            — valor de uma chave               (settings.read)
    PUT  /settings/key/{key}            — atualizar valor                  (settings.write)
    POST /settings/seed                 — restaurar padrões                (settings.write)
    GET  /settings/permissions/matrix   — matriz role → permissões         (settings.read)
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any

from app.infrastructure.database.dependencies import get_db
from sqlalchemy.orm import Session

from app.application.settings.settings_service import SettingsService, SettingsError
from app.presentation.dependencies import (
    require_permission,
    get_tenant_context,
)
from app.domain.security.models import TenantContext, ROLE_PERMISSIONS

router = APIRouter(prefix="/settings", tags=["Settings"])


def _svc(db: Session = Depends(get_db)) -> SettingsService:
    return SettingsService(db)


class SettingUpdate(BaseModel):
    value: Any


class SeedResult(BaseModel):
    created: int


@router.get("")
def get_all_settings(
    svc: SettingsService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("settings.read")),
):
    return {"categories": svc.grouped()}


@router.get("/category/{category}")
def get_category(
    category: str,
    svc: SettingsService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("settings.read")),
):
    rows = svc.list_by_category(category)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Categoria '{category}' não encontrada.")
    return {"category": category, "settings": [svc.to_dict(r) for r in rows]}


@router.get("/key/{key}")
def get_key(
    key: str,
    svc: SettingsService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("settings.read")),
):
    row = svc.get(key)
    if not row:
        raise HTTPException(status_code=404, detail=f"Configuração '{key}' não encontrada.")
    return svc.to_dict(row)


@router.put("/key/{key}")
def update_key(
    key: str,
    body: SettingUpdate,
    svc: SettingsService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("settings.write")),
):
    try:
        row = svc.update(key, body.value, updated_by=ctx.user_id)
    except SettingsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return svc.to_dict(row)


@router.post("/seed", response_model=SeedResult)
def seed(
    svc: SettingsService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("settings.write")),
):
    return SeedResult(created=svc.seed_defaults())


@router.get("/permissions/matrix")
def permissions_matrix(ctx: TenantContext = Depends(require_permission("settings.read"))):
    """Matriz role → permissões (catálogo de RBAC granular)."""
    matrix = {}
    for role, perms in ROLE_PERMISSIONS.items():
        matrix[role.value] = sorted(perms)
    return {
        "roles": matrix,
        "me": {"role": ctx.role.value, "permissions": sorted(ctx.permissions)},
    }


@router.get("/permissions/me")
def my_permissions(ctx: TenantContext = Depends(get_tenant_context)):
    """Permissões efetivas do usuário logado (qualquer autenticado)."""
    return {"role": ctx.role.value, "permissions": sorted(ctx.permissions)}
