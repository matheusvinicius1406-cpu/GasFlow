"""Link público de rastreio (Fase 7.2).

- `POST /public/tracking/link` — operador/admin **autenticado** gera o link.
- `GET  /public/tracking/{token}` — **sem auth**, somente leitura, sem PII.

O token é stateless (HMAC com escopo `public_tracking` + expiração); não há
tabela nova nem sessão. O cliente final só recebe coordenadas e o horário da
última posição — nada de nome, telefone ou endereço.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession

from app.application.tracking.public_tracking import (
    DEFAULT_TTL_SECONDS,
    MAX_TTL_SECONDS,
    issue_public_tracking_token,
    verify_public_tracking_token,
)
from app.domain.security.models import SystemRole, TenantContext
from app.presentation.dependencies import require_role

router = APIRouter(prefix="/public/tracking", tags=["public-tracking"])


def _db() -> DBSession:
    from app.infrastructure.database.init_db import engine

    return DBSession(bind=engine)


@router.post("/link")
async def create_public_link(
    driver_id: str = Query(..., min_length=1),
    ttl_seconds: int = Query(DEFAULT_TTL_SECONDS, ge=60, le=MAX_TTL_SECONDS),
    ctx: TenantContext = Depends(require_role(SystemRole.ADMIN, SystemRole.OPERATOR)),
):
    """Gera o token do link público para um entregador do próprio tenant."""
    from app.infrastructure.repositories.delivery_repository import (
        SQLAlchemyDeliveryDriverRepository,
    )

    db = _db()
    try:
        driver = SQLAlchemyDeliveryDriverRepository(db, tenant_id=ctx.tenant_id).find_by_id_as_model(driver_id)
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
    finally:
        db.close()

    token = issue_public_tracking_token(tenant_id=ctx.tenant_id, driver_id=driver_id, ttl_seconds=ttl_seconds)
    return {"token": token, "expires_in": ttl_seconds}


@router.get("/{token}")
async def public_tracking_snapshot(token: str):
    """Snapshot somente-leitura da posição atual (sem autenticação).

    Sem PII por construção: só `driver_id`, coordenadas e horário.
    """
    from app.infrastructure.repositories.delivery_persistence_repository import (
        SQLAlchemyDriverLocationRepository,
    )

    payload = verify_public_tracking_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Link inválido ou expirado")

    tenant_id, driver_id = str(payload["t"]), str(payload["d"])

    db = _db()
    try:
        last = SQLAlchemyDriverLocationRepository(db).get_location(tenant_id, driver_id)
        if not last:
            raise HTTPException(status_code=404, detail="Sem posição recente")
        return {
            "driver_id": driver_id,
            "latitude": last.latitude,
            "longitude": last.longitude,
            "updated_at": last.timestamp.isoformat() if last.timestamp else None,
        }
    finally:
        db.close()
