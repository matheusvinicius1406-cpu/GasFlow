"""Driver Self API — entregador autenticado pela auth principal (`/auth/login`).

Namespace `/driver/*`, protegido por `require_driver`. Reaproveita a sessão do
operador (access JWT + refresh), logo herda de graça o gate de
`must_change_password` no HTTP e no WebSocket — sem um segundo subsistema de
login.

Escopo: toda query filtra por `ctx.tenant_id` E `ctx.driver_id`. O `driver_id`
é o `delivery_drivers.codigo`, a identidade usada em `delivery_records`.

O login legado em `driver_api.py` (`/api/driver/v1/auth/login`) fica como
caminho antigo — ver `# LEGACY` lá. Não estenda aquele fluxo.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.domain.security.models import SystemRole, TenantContext
from app.presentation.dependencies import require_driver, require_role

# Handlers compartilhados das ações de entrega — a nota completa está na seção
# "Ações de entrega" mais abaixo.
from app.presentation.api.logistics.driver_api import (
    ActionRequest,
    LocationUpdate,
    handle_accept_delivery,
    handle_arrive_delivery,
    handle_complete_delivery,
    handle_fail_delivery,
    handle_start_delivery,
    handle_update_location,
)

router = APIRouter(prefix="/driver", tags=["driver-self"])

# Fase 4 — ingestão em lote de posições
MAX_LOCATION_BATCH = 500


def _db() -> DBSession:
    from app.infrastructure.database.init_db import engine

    return DBSession(bind=engine)


@router.get("/deliveries")
async def list_my_deliveries(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: TenantContext = Depends(require_driver),
):
    """Lista apenas as entregas do próprio entregador, no próprio tenant."""
    if not ctx.driver_id:
        # Invariante: role=DRIVER ⟹ driver_id preenchido. Defensivo — o gate de
        # `require_driver` já restringe o acesso por role.
        raise HTTPException(status_code=403, detail="Driver not linked to a delivery_driver")

    from app.infrastructure.repositories.delivery_persistence_repository import (
        SQLAlchemyDeliveryPersistenceRepository,
    )

    db = _db()
    try:
        repo = SQLAlchemyDeliveryPersistenceRepository(db, tenant_id=ctx.tenant_id)
        records = repo.list_deliveries(status=status, driver_id=ctx.driver_id, limit=limit, offset=offset)
        return {"deliveries": [r.to_dict() for r in records]}
    finally:
        db.close()


@router.get("/me")
async def get_my_profile(ctx: TenantContext = Depends(require_driver)):
    """Perfil do entregador autenticado (nome, janela LGPD e cadência).

    Espelha o contrato do `/api/v1/driver/me` legado, mas autenticado pela auth
    principal — é o que o app do entregador migrado consome.
    """
    if not ctx.driver_id:
        raise HTTPException(status_code=403, detail="Driver not linked to a delivery_driver")

    from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository

    db = _db()
    try:
        repo = SQLAlchemyDeliveryDriverRepository(db, tenant_id=ctx.tenant_id)
        model = repo.find_by_id_as_model(ctx.driver_id)
        if not model:
            raise HTTPException(status_code=404, detail="Driver not found")

        tracking_interval = 120
        work_hours: Optional[str] = None
        try:
            from app.application.settings.settings_service import SettingsService

            svc = SettingsService(db)
            tracking_interval = max(15, int(svc.get_value("driver.tracking.interval_seconds", 120)))
            start = str(svc.get_value("driver.work_hours.start", "06:00"))
            end = str(svc.get_value("driver.work_hours.end", "22:00"))
            if start and end:
                work_hours = f"{start}-{end}"
        except Exception:
            pass

        # Fase 3.3: distância do dia calculada do histórico (antes era sempre 0).
        from app.infrastructure.repositories.delivery_persistence_repository import (
            SQLAlchemyDriverLocationRepository,
        )

        today_distance_km = SQLAlchemyDriverLocationRepository(db).today_distance_km(ctx.tenant_id, model.codigo)

        return {
            "driver_id": model.codigo,
            "name": model.nome,
            "phone": model.telefone,
            "status": model.status or "AVAILABLE",
            "active": bool(model.ativo),
            "tenant_id": model.tenant_id or "default",
            "tracking_interval_seconds": tracking_interval,
            "work_hours": work_hours,
            "today_distance_km": today_distance_km,
        }
    finally:
        db.close()


# ── Ações de entrega — auth principal ─────────────────────────────────────
#
# As ações existiam só em `/api/v1/driver/*` (`driver_v1` → `_authenticate_driver`),
# que aceita **sessão de driver no banco** ou **JWT de escopo `mobile`**. O app
# loga em `/auth/login` (auth principal) e não tem nenhum dos dois → 401 em
# aceitar/iniciar/concluir/falhar. Aqui as mesmas ações ficam no namespace do
# app, atrás de `require_driver`, escopadas por `ctx.tenant_id` e `ctx.driver_id`.
#
# Os handlers de `driver_api.py` são reaproveitados: a lógica de transição de
# estado, a idempotência DB-backed e a publicação no barramento são as mesmas.
# O passo seguinte da migração move esses handlers para um módulo compartilhado
# e aposenta `driver_api`/`driver_v1` — junto da página web `/driver`, que ainda
# é o outro consumidor do namespace antigo.


def _shared_ctx(ctx: TenantContext) -> Dict[str, Any]:
    """Adapta o `TenantContext` ao dict que os handlers compartilhados esperam."""
    if not ctx.driver_id:
        raise HTTPException(status_code=403, detail="Driver not linked to a delivery_driver")
    return {"tenant_id": ctx.tenant_id, "driver_id": ctx.driver_id, "role": str(ctx.role)}


@router.post("/deliveries/{delivery_id}/accept")
async def accept_my_delivery(
    delivery_id: str,
    req: ActionRequest = ActionRequest(),
    ctx: TenantContext = Depends(require_driver),
):
    """Aceita a entrega atribuída ao próprio entregador."""
    return await handle_accept_delivery(_shared_ctx(ctx), delivery_id, req)


@router.post("/deliveries/{delivery_id}/start")
async def start_my_delivery(
    delivery_id: str,
    req: ActionRequest = ActionRequest(),
    ctx: TenantContext = Depends(require_driver),
):
    """Inicia a rota da entrega do próprio entregador."""
    return await handle_start_delivery(_shared_ctx(ctx), delivery_id, req)


@router.post("/deliveries/{delivery_id}/arrive")
async def arrive_my_delivery(
    delivery_id: str,
    req: ActionRequest = ActionRequest(),
    ctx: TenantContext = Depends(require_driver),
):
    """Marca chegada ao destino."""
    return await handle_arrive_delivery(_shared_ctx(ctx), delivery_id, req)


@router.post("/deliveries/{delivery_id}/complete")
async def complete_my_delivery(
    delivery_id: str,
    req: ActionRequest = ActionRequest(),
    ctx: TenantContext = Depends(require_driver),
):
    """Conclui a entrega (com prova opcional)."""
    return await handle_complete_delivery(_shared_ctx(ctx), delivery_id, req)


@router.post("/deliveries/{delivery_id}/fail")
async def fail_my_delivery(
    delivery_id: str,
    req: ActionRequest,
    ctx: TenantContext = Depends(require_driver),
):
    """Reporta falha na entrega."""
    return await handle_fail_delivery(_shared_ctx(ctx), delivery_id, req)


# ── Fase 4: ingestão em lote + realtime ────────────────────────────────────


class DriverLocationPoint(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy_m: Optional[float] = None
    speed_kmh: Optional[float] = None
    heading_deg: Optional[float] = None
    recorded_at: Optional[datetime] = None


class DriverLocationsBatch(BaseModel):
    points: List[DriverLocationPoint] = Field(default_factory=list)


@router.post("/locations")
async def ingest_locations(
    payload: DriverLocationsBatch,
    ctx: TenantContext = Depends(require_driver),
):
    """Recebe o lote de posições do próprio entregador (app/offline queue).

    - Escopo garantido por `require_driver` + `ctx.driver_id` (nunca aceita de
      outro entregador/tenant).
    - Work-hours (LGPD) e histórico append-only ficam em `DriverLocationService`.
    - Publica no barramento realtime existente (`driver.location_updated`),
      que já roteia para `tenant:{id}` / `driver:{id}` / `operations:{id}`.
    """
    if not ctx.driver_id:
        raise HTTPException(status_code=403, detail="Driver not linked to a delivery_driver")
    if len(payload.points) > MAX_LOCATION_BATCH:
        raise HTTPException(status_code=400, detail=f"batch too large (max {MAX_LOCATION_BATCH})")
    if not payload.points:
        return {"accepted": 0}

    from app.application.delivery.driver_location_service import (
        DriverLocationService,
        WorkHoursViolation,
    )

    db = _db()
    try:
        service = DriverLocationService(db, ctx.tenant_id, ctx.driver_id or "")
        try:
            result = service.ingest_batch([p.model_dump() for p in payload.points])
        except WorkHoursViolation as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"accepted": int(result.get("accepted", 0))}
    finally:
        db.close()


@router.post("/location")
async def update_my_location(
    req: LocationUpdate,
    ctx: TenantContext = Depends(require_driver),
):
    """Posição do próprio entregador — alias principal do ingest legado.

    Mesma semântica do handler compartilhado: janela LGPD (403 fora dela),
    throttle de 10 s e evento realtime. O caminho em lote
    (`POST /driver/locations`) segue sendo o preferido para o app offline.
    """
    return await handle_update_location(_shared_ctx(ctx), req)


@router.get("/locations/history")
async def get_location_history(
    driver_id: str = Query(..., min_length=1),
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
    limit: int = Query(500, ge=1, le=5000),
    ctx: TenantContext = Depends(require_role(SystemRole.ADMIN, SystemRole.OPERATOR)),
):
    """Histórico de posições de um entregador (operador/admin), escopado por tenant."""
    from app.infrastructure.repositories.delivery_persistence_repository import (
        SQLAlchemyDriverLocationRepository,
    )

    db = _db()
    try:
        repo = SQLAlchemyDriverLocationRepository(db)
        rows = repo.get_history(ctx.tenant_id, driver_id, from_ts=from_ts, to_ts=to_ts, limit=limit)
        return {
            "driver_id": driver_id,
            "count": len(rows),
            "points": [
                {
                    "latitude": r.latitude,
                    "longitude": r.longitude,
                    "accuracy_m": r.accuracy_m,
                    "speed_kmh": r.speed_kmh,
                    "heading_deg": r.heading_deg,
                    "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
                }
                for r in rows
            ],
        }
    finally:
        db.close()
