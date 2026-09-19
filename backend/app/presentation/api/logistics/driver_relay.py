"""
Driver Relay Ingest — Fix do elo morto da cadeia da rua (rastreador).

Cadeia completa: Mobile (GPS, só em rota) ──HTTPS──▶ Relay (nuvem) ──WS──▶
Desktop ──POST /api/v1/internal/driver/location/relay──▶ backend embutido
──▶ driver_locations ──▶ mapa do operador (polling 30s).

O relay é um "pipe burro": o payload que chega não carrega JWT do entregador.
A autenticação é de MÁQUINA, pelo mesmo padrão service-to-service do
/whatsapp/incoming (X-GasFlow-Key, fail-closed). JWT de usuário NÃO vale —
um token vazado não pode injetar posição GPS de entregador.

Regras de negócio ficam no handler compartilhado handle_update_location
(throttle de 10s + work-hours LGPD + upsert + evento realtime). Adições
deste endpoint:

- driver_id do payload validado contra os motoristas do tenant — o relay
  é confiável para TRANSPORTAR, não para ATRIBUIR identidade
- audit `driver.location.ingest_relay` com platform="desktop" e
  actor_type="SYSTEM" — distinguível do POST direto do app
  (`driver.location.batch`, platform="mobile", actor_type="DRIVER")
"""

import hmac
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.presentation.api.logistics.driver_api import (
    LocationUpdate,
    _get_db_session,
    handle_update_location,
)

# Montado sob /api/v1 (api/v1/router.py) — caminho final:
# /api/v1/internal/driver/location/relay
router = APIRouter(prefix="/internal/driver", tags=["Driver Relay"])


class RelayLocationPayload(BaseModel):
    """Espelha o payload `driver:location` emitido pelo relay (DEPLOY.md)."""

    model_config = ConfigDict(populate_by_name=True)

    driver_id: str = Field(..., min_length=1)
    latitude: float = Field(..., ge=-90, le=90, alias="lat")
    longitude: float = Field(..., ge=-180, le=180, alias="lng")
    accuracy: Optional[float] = None
    speed: Optional[float] = None
    bearing: Optional[float] = None
    recorded_at: Optional[str] = None


class RelayLocationBatch(BaseModel):
    """Lote de posições de UM motorista (o relay agrupa por driver)."""

    tenant_id: str = Field(default="default", min_length=1)
    driver_id: str = Field(..., min_length=1)
    positions: List[RelayLocationPayload] = Field(..., min_length=1, max_length=50)


def _require_relay_service_key(x_gasflow_key: Optional[str] = Header(None)) -> None:
    """Fail-closed: só passa com a chave de serviço configurada e igual.

    Mesma confiança e mesma env do /whatsapp/incoming
    (WHATSAPP_SERVICE_KEY/MARCOS_GAS_API_KEY).
    """
    from app.core.config import settings

    service_key = settings.whatsapp_service_key
    if not service_key or not x_gasflow_key or not hmac.compare_digest(service_key, x_gasflow_key):
        raise HTTPException(status_code=401, detail="Service key required")


def _audit_relay_ingest(db, driver_id: str, tenant_id: str, details: dict, result: str = "SUCCESS") -> None:
    """Audit da ingestão via relay (best-effort, sem coordenadas — LGPD).

    Distinguível do POST direto do app: action `driver.location.ingest_relay`,
    actor_type="SYSTEM" e platform="desktop" (o app usa action
    `driver.location.batch`, platform="mobile", actor_type="DRIVER").
    """
    try:
        from app.infrastructure.repositories.auth_model import AuthAuditModel

        db.add(
            AuthAuditModel(
                id=str(uuid.uuid4()),
                actor_id="service:relay",
                actor_type="SYSTEM",
                tenant_id=tenant_id,
                action="driver.location.ingest_relay",
                resource="driver_location",
                resource_id=driver_id,
                result=result,
                timestamp=datetime.utcnow(),
                ip_address="127.0.0.1",
                user_agent="",
                platform="desktop",
                details=details,
            )
        )
        db.commit()
    except Exception:  # pragma: no cover — audit é best-effort
        db.rollback()


@router.post("/location/relay", summary="Ingest driver location from relay (service-to-service)")
async def relay_driver_location(
    batch: RelayLocationBatch,
    _: None = Depends(_require_relay_service_key),
):
    """Ingest de posições vindas da rua: relay → desktop → backend.

    Valida o driver_id contra os motoristas do tenant (posição só é aceita
    DE um motorista real e ativo) e reusa o handler compartilhado por
    posição (throttle 10s + work-hours + upsert + evento realtime).
    """
    from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository

    db = _get_db_session()
    try:
        driver_repo = SQLAlchemyDeliveryDriverRepository(db, tenant_id=batch.tenant_id)
        driver_model = driver_repo.find_by_id_as_model(batch.driver_id)
        if not driver_model or not driver_model.ativo:
            _audit_relay_ingest(
                db,
                batch.driver_id,
                batch.tenant_id,
                {"reason": "unknown_driver", "positions": len(batch.positions)},
                result="REJECTED",
            )
            raise HTTPException(status_code=404, detail="Driver not found")

        accepted, throttled = 0, 0
        for pos in batch.positions:
            ctx = {"driver_id": batch.driver_id, "tenant_id": batch.tenant_id, "role": "DRIVER", "scope": "relay"}
            # Converte para o payload do handler compartilhado (app direto e
            # relay usam o mesmo ingest); recorded_at não é consumido a jusante.
            loc = LocationUpdate(
                latitude=pos.latitude,
                longitude=pos.longitude,
                accuracy=pos.accuracy,
                speed=pos.speed,
                bearing=pos.bearing,
            )
            result = await handle_update_location(ctx, loc)
            if result.get("throttled"):
                throttled += 1
            else:
                accepted += 1

        _audit_relay_ingest(
            db,
            batch.driver_id,
            batch.tenant_id,
            {"accepted": accepted, "throttled": throttled, "received": len(batch.positions)},
        )
        return {"success": True, "accepted": accepted, "throttled": throttled}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
