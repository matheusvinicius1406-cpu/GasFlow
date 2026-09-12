"""StockDailySnapshotService — snapshot diário de estoque (P0 3.7).

Grava, para cada produto com inventário, o estado cheios/vazios:
- initial_full/initial_empty: do snapshot do dia anterior (closing) ou,
  no primeiro dia, dos valores atuais.
- closing_full/closing_empty: valores atuais do inventário.

Idempotente por UNIQUE (tenant_id, snapshot_date, product_codigo):
o job faz upsert — rodar duas vezes no mesmo dia não duplica nem sobrescreve
closings de dias passados.

Timezone: America/Belem por padrão (configurável via STOCK_SNAPSHOT_TZ).
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.infrastructure.repositories.inventory_model import InventoryModel
from app.infrastructure.repositories.rbac_model import StockDailySnapshotModel

logger = logging.getLogger(__name__)

DEFAULT_TZ = "America/Belem"


def _local_today(tz_name: str) -> date:
    """Data 'de hoje' no fuso configurado."""
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        logger.warning("timezone inválida '%s' — usando %s", tz_name, DEFAULT_TZ)
        tz = ZoneInfo(DEFAULT_TZ)
    return datetime.now(tz).date()


class StockDailySnapshotService:
    """Serviço de snapshot diário — chamado pelo poller de automação."""

    def __init__(self, db: Session, tenant_id: str = "default"):
        self.db = db
        self.tenant_id = tenant_id

    # ── API principal ────────────────────────────────────────

    def run_daily_snapshot(self, tz_name: Optional[str] = None) -> Dict[str, int]:
        """Executa o snapshot para a data local de hoje.

        Se o job ficou fora do ar e pulou dias, grava snapshots para os dias
        faltantes (last+1 … today-1) com os valores atuais — melhor estimativa
        disponível — SEM reescrever o closing do último dia já gravado.
        Garante que initial(d+1) == closing(d) na cadeia.

        Retorna contadores: {"created": N, "carryover": N}.
        """
        tz_name = tz_name or os.getenv("STOCK_SNAPSHOT_TZ", DEFAULT_TZ)
        today = _local_today(tz_name)

        last = self._last_snapshot_date()
        carryover = 0
        created = 0
        if last is None:
            created = self._snapshot_day(today)
        else:
            # Dias faltantes entre last e today (exclusive) — carry-over.
            d = last + timedelta(days=1)
            while d < today:
                carryover += self._snapshot_day(d)
                d += timedelta(days=1)
            created = self._snapshot_day(today)
        return {"created": created, "carryover": carryover}

    def ensure_initial_snapshot(self, tz_name: Optional[str] = None) -> int:
        """Garante o snapshot do dia corrente (idempotente) — usado no boot.

        No primeiro dia de operação, initial = closing = valores atuais.
        """
        tz_name = tz_name or os.getenv("STOCK_SNAPSHOT_TZ", DEFAULT_TZ)
        today = _local_today(tz_name)
        return self._snapshot_day(today)

    # ── Internos ─────────────────────────────────────────────

    def _last_snapshot_date(self) -> Optional[date]:
        row = (
            self.db.query(StockDailySnapshotModel.snapshot_date)
            .filter(StockDailySnapshotModel.tenant_id == self.tenant_id)
            .order_by(StockDailySnapshotModel.snapshot_date.desc())
            .first()
        )
        return row[0] if row else None

    def _snapshot_day(self, day: date) -> int:
        """Grava/atualiza snapshots do dia. Retorna nº de snapshots criados."""
        created = 0
        inventories = self.db.query(InventoryModel).filter(InventoryModel.tenant_id == self.tenant_id).all()

        # previous closing por produto (para initial)
        prev = {
            p.product_codigo: p
            for p in self.db.query(StockDailySnapshotModel)
            .filter(
                StockDailySnapshotModel.tenant_id == self.tenant_id,
                StockDailySnapshotModel.snapshot_date < day,
            )
            .order_by(StockDailySnapshotModel.snapshot_date.desc())
            .all()
        }

        for inv in inventories:
            full = int(inv.quantity_full or 0)
            empty = int(inv.quantity_empty or 0)

            existing = (
                self.db.query(StockDailySnapshotModel)
                .filter(
                    StockDailySnapshotModel.tenant_id == self.tenant_id,
                    StockDailySnapshotModel.snapshot_date == day,
                    StockDailySnapshotModel.product_codigo == inv.product_codigo,
                )
                .first()
            )

            prev_snap = prev.get(inv.product_codigo)
            if prev_snap is not None:
                initial_full = prev_snap.closing_full
                initial_empty = prev_snap.closing_empty
            else:
                # Primeiro dia: initial = valores atuais
                initial_full, initial_empty = full, empty

            if existing:
                # Upsert idempotente: atualiza closing só se mudou (evita
                # escrita redundante a cada tick do poller); initial preservado.
                if existing.closing_full != full or existing.closing_empty != empty:
                    existing.closing_full = full
                    existing.closing_empty = empty
                    existing.updated_at = datetime.utcnow()
            else:
                self.db.add(
                    StockDailySnapshotModel(
                        tenant_id=self.tenant_id,
                        snapshot_date=day,
                        product_codigo=inv.product_codigo,
                        initial_full=initial_full,
                        initial_empty=initial_empty,
                        closing_full=full,
                        closing_empty=empty,
                    )
                )
                created += 1

        self.db.commit()
        return created
