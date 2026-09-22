"""Link público de rastreio (Parte 1 — fixes 3 e 4).

- `POST /public/tracking/link`            — operador/admin **autenticado** gera o link.
- `POST /public/tracking/revoke/{id}`     — **ADMIN** revoga todos os links do entregador.
- `GET  /public/tracking/{token}`         — **sem auth**, somente leitura, sem PII.

Status codes que importam:
- **401** link inválido/expirado (assinatura, escopo ou `exp`);
- **410 Gone** link válido porém **revogado** (epoch divergente) — o link
  existiu e foi cancelado, então não é 401;
- **404** entregador inexistente no tenant ou sem posição recente.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession

from app.application.tracking.public_tracking import (
    DEFAULT_TTL_S,
    MAX_TTL_S,
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
    ttl_seconds: int = Query(DEFAULT_TTL_S, gt=0, le=MAX_TTL_S),
    ctx: TenantContext = Depends(require_role(SystemRole.ADMIN, SystemRole.OPERATOR)),
):
    """Gera o token do link público para um entregador do próprio tenant."""
    from app.infrastructure.repositories.delivery_repository import (
        SQLAlchemyDeliveryDriverRepository,
    )

    db = _db()
    try:
        repo = SQLAlchemyDeliveryDriverRepository(db, tenant_id=ctx.tenant_id)
        driver = repo.find_by_id_as_model(driver_id)
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        epoch = repo.get_tracking_epoch(driver_id)
    finally:
        db.close()

    token = issue_public_tracking_token(
        tenant_id=ctx.tenant_id,
        driver_id=driver_id,
        ttl_seconds=ttl_seconds,
        epoch=epoch,
    )
    return {"token": token, "expires_in": ttl_seconds, "epoch": epoch}


@router.post("/revoke/{driver_id}")
async def revoke_public_links(
    driver_id: str,
    ctx: TenantContext = Depends(require_role(SystemRole.ADMIN)),
):
    """Revoga **todos** os links públicos já emitidos para o entregador."""
    from app.infrastructure.repositories.delivery_repository import (
        SQLAlchemyDeliveryDriverRepository,
    )

    db = _db()
    try:
        repo = SQLAlchemyDeliveryDriverRepository(db, tenant_id=ctx.tenant_id)
        if not repo.find_by_id_as_model(driver_id):
            raise HTTPException(status_code=404, detail="Driver not found")
        epoch = repo.bump_tracking_epoch(driver_id)
    finally:
        db.close()

    return {"revoked": True, "epoch": epoch}


@router.get("/{token}")
async def public_tracking_snapshot(token: str):
    """Snapshot somente-leitura da posição atual (sem autenticação).

    Sem PII por construção: só `driver_id`, coordenadas e horário.
    """
    from app.infrastructure.repositories.delivery_persistence_repository import (
        SQLAlchemyDriverLocationRepository,
    )
    from app.infrastructure.repositories.delivery_repository import (
        SQLAlchemyDeliveryDriverRepository,
    )

    payload = verify_public_tracking_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Link inválido ou expirado")

    tenant_id, driver_id = str(payload["t"]), str(payload["d"])

    db = _db()
    try:
        driver_repo = SQLAlchemyDeliveryDriverRepository(db, tenant_id=tenant_id)
        driver = driver_repo.find_by_id_as_model(driver_id)
        if not driver:
            # Não vaza se o entregador existe noutro tenant: para este link,
            # simplesmente não há o que mostrar.
            raise HTTPException(status_code=404, detail="Sem posição recente")

        if int(payload.get("e", 0)) != driver_repo.get_tracking_epoch(driver_id):
            raise HTTPException(status_code=410, detail="Link revogado")

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
