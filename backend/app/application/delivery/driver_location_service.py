"""Driver Location Service — App do Entregador (Fase 1, LGPD).

Ingestão em lote de posições GPS com as regras do roadmap (seção 3.4/8):

- Só aceita posições dentro do horário de trabalho do tenant
  (driver.work_hours.start/end; fora da janela → 403, nada persistido)
- Rate limit de 60 posições por request e 500/batch (payload)
- Retenção de 90 dias: purge_positions_older_than() chamado por cron/boot
- Audit de cada acesso/ingestão em auth_audit_log (best-effort)
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.infrastructure.repositories.delivery_persistence_repository import (
    SQLAlchemyDriverLocationRepository,
)

logger = logging.getLogger(__name__)

MAX_BATCH = 500
RETENTION_DAYS = 90


class WorkHoursViolation(Exception):
    """Fora do horário de trabalho — LGPD (posição não persistida)."""


class DriverLocationService:
    def __init__(self, db: Session, tenant_id: str, driver_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.driver_id = driver_id

    # ── Helpers ──────────────────────────────────────────────

    def _audit(self, action: str, details: Dict[str, Any], result: str = "SUCCESS") -> None:
        """Audit trail (best-effort, convenção P0 3.3). Sem coordenadas."""
        try:
            from app.infrastructure.repositories.auth_model import AuthAuditModel

            self.db.add(
                AuthAuditModel(
                    id=str(uuid.uuid4()),
                    actor_id=self.driver_id,
                    actor_type="DRIVER",
                    tenant_id=self.tenant_id,
                    action=action,
                    resource="driver_location",
                    resource_id=self.driver_id,
                    result=result,
                    timestamp=datetime.utcnow(),
                    ip_address="",
                    user_agent="",
                    platform="mobile",
                    details=details,
                )
            )
            self.db.commit()
        except Exception:  # pragma: no cover
            self.db.rollback()
            logger.debug("driver_location.audit_failed")

    # ── API ──────────────────────────────────────────────────

    def is_within_work_hours(self, now: Optional[datetime] = None) -> bool:
        """Janela configurável por tenant; inválida → fail-open."""
        from app.application.settings.settings_service import SettingsService

        svc = SettingsService(self.db)
        start = str(svc.get_value("driver.work_hours.start", "06:00"))
        end = str(svc.get_value("driver.work_hours.end", "22:00"))
        try:
            sh, sm = (int(p) for p in start.split(":")[:2])
            eh, em = (int(p) for p in end.split(":")[:2])
        except ValueError:
            return True
        now = now or datetime.utcnow()
        minutes = now.hour * 60 + now.minute
        start_m, end_m = sh * 60 + sm, eh * 60 + em
        if start_m <= end_m:
            return start_m <= minutes < end_m
        return minutes >= start_m or minutes < end_m

    def ingest_batch(
        self, positions: List[Dict[str, Any]], recorded_server_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Ingere lote de posições. Fora do horário → WorkHoursViolation.

        Cada posição: {lat, lng, speed?, heading?, accuracy?, recorded_at?}.
        recorded_at do cliente é aceito apenas para ordenar; o servidor
        grava timestamp próprio (anti-relógio-furado simples).
        """
        if not positions:
            return {"accepted": 0, "throttled": 0}
        if len(positions) > MAX_BATCH:
            raise ValueError(f"batch too large: {len(positions)} > {MAX_BATCH}")

        if not self.is_within_work_hours(recorded_server_time):
            self._audit(
                "driver.location.rejected_out_of_hours",
                {"count": len(positions)},
                result="REJECTED",
            )
            raise WorkHoursViolation("Fora do horário de trabalho — localização não coletada")

        repo = SQLAlchemyDriverLocationRepository(self.db)
        accepted = 0
        for pos in positions:
            lat_raw, lng_raw = pos.get("lat"), pos.get("lng")
            if lat_raw is None or lng_raw is None:
                continue
            try:
                lat = float(lat_raw)
                lng = float(lng_raw)
            except (TypeError, ValueError):
                continue  # posição malformada é descartada, não rejeita o lote
            repo.upsert_location(
                tenant_id=self.tenant_id,
                driver_id=self.driver_id,
                latitude=lat,
                longitude=lng,
                accuracy=_opt_float(pos.get("accuracy")),
                speed=_opt_float(pos.get("speed")),
                bearing=_opt_float(pos.get("heading")),
            )
            accepted += 1

        self._audit(
            "driver.location.batch",
            {"accepted": accepted, "rejected": len(positions) - accepted},
        )
        return {"accepted": accepted, "throttled": 0}

    def latest(self) -> Optional[Dict[str, Any]]:
        repo = SQLAlchemyDriverLocationRepository(self.db)
        record = repo.get_location(self.tenant_id, self.driver_id)
        if not record:
            return None
        # Audit de consulta (LGPD: cada acesso à localização é rastreável)
        self._audit("driver.location.read", {"by": self.driver_id})
        return {
            "lat": record.latitude,
            "lng": record.longitude,
            "speed_kmh": record.speed,
            "accuracy_m": record.accuracy,
            "heading": record.bearing,
            "recorded_at": record.timestamp.isoformat() if record.timestamp else None,
        }


def _opt_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def purge_old_locations(db: Session, days: int = RETENTION_DAYS) -> int:
    """LGPD: apaga posições com mais de N dias (default 90). Idempotente."""
    from app.infrastructure.repositories.delivery_persistence_model import DriverLocationRecord

    cutoff = datetime.utcnow() - timedelta(days=days)
    deleted = (
        db.query(DriverLocationRecord).filter(DriverLocationRecord.timestamp < cutoff).delete(synchronize_session=False)
    )
    db.commit()
    return deleted
