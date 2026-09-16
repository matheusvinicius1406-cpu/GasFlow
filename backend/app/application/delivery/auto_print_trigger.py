"""
Auto-print trigger — F3

Fila de auto-print do print agent: quando um pedido entra em um dos status
configurados (setting `printer.auto_print.min_status`, default
"PAID,CONFIRMED"), um job de impressão é criado uma única vez.

Idempotência por pedido: `auto_printed_orders` guarda os order_id já
imprimidos automaticamente (evita reimpressão em eventos repetidos);
impressão manual (is_reprint) nunca é bloqueada.
"""

import threading
from typing import Any, Dict, Optional

from app.infrastructure.printing.print_agent import get_print_agent
from app.core.logging import setup_logging

logger = setup_logging("INFO")


class AutoPrintTrigger:
    """Cria print jobs automaticamente para pedidos em status elegíveis."""

    def __init__(self):
        self._lock = threading.Lock()
        # order_id -> True (pedido já auto-impresso nesta sessão do agente)
        self._auto_printed_orders: Dict[str, bool] = {}

    # ── Config ─────────────────────────────────────────────────

    @staticmethod
    def _load_allowed_statuses() -> set:
        """Lê o setting printer.auto_print.min_status (default PAID,CONFIRMED).

        Falha aberta a conservadorismo: sem settings acessível, usa o default
        (nunca imprime tudo).
        """
        default = {"PAID", "CONFIRMED"}
        try:
            from sqlalchemy.orm import Session as _Session
            from app.infrastructure.database.init_db import engine
            from app.application.settings.settings_service import SettingsService

            session = _Session(bind=engine)
            try:
                raw = SettingsService(session).get_value("printer.auto_print.min_status", "PAID,CONFIRMED")
            finally:
                session.close()
            if isinstance(raw, str) and raw.strip():
                statuses = {s.strip().upper() for s in raw.split(",") if s.strip()}
                return statuses or default
            if isinstance(raw, (list, tuple, set)):
                statuses = {str(s).strip().upper() for s in raw if str(s).strip()}
                return statuses or default
            return default
        except Exception:
            logger.warning("auto_print_status_lookup_failed — usando default PAID,CONFIRMED")
            return default

    # ── Idempotência ───────────────────────────────────────────

    def already_printed(self, order_id: str) -> bool:
        with self._lock:
            return order_id in self._auto_printed_orders

    def mark_printed(self, order_id: str) -> None:
        with self._lock:
            self._auto_printed_orders[order_id] = True

    # ── Trigger principal ──────────────────────────────────────

    def maybe_auto_print(
        self,
        order_id: str,
        tenant_id: str,
        order_status: str,
        order_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Avalia se o pedido deve ser impresso agora.

        Regras:
        - status do pedido precisa estar no setting printer.auto_print.min_status
        - 1 job por pedido (idempotente em eventos repetidos)
        - retorno explica a decisão (skipped_reason) para auditoria
        """
        allowed = self._load_allowed_statuses()
        status = (order_status or "").upper()
        if status not in allowed:
            reason = f"status_not_eligible:{status or 'EMPTY'}"
            logger.info("auto_print.skipped", extra={"order_id": order_id, "reason": reason})
            return {"created": False, "skipped_reason": reason}

        with self._lock:
            if order_id in self._auto_printed_orders:
                return {"created": False, "skipped_reason": "already_auto_printed"}
            # Marca ANTES de criar o job: concorrência (dois workers no mesmo
            # evento) não gera dois jobs.
            self._auto_printed_orders[order_id] = True

        try:
            agent = get_print_agent()
            job = agent.create_print_job(
                order_id=order_id,
                tenant_id=tenant_id,
                order_data=order_data or {"codigo": order_id},
                requested_by="auto_print",
                is_reprint=False,
            )
            logger.info("auto_print.job_created", extra={"order_id": order_id, "job_id": job.id})
            return {"created": True, "job_id": job.id}
        except Exception:
            # Job não criado: libera a marca para tentar novamente no próximo evento.
            with self._lock:
                self._auto_printed_orders.pop(order_id, None)
            logger.exception("auto_print.job_failed", extra={"order_id": order_id})
            return {"created": False, "skipped_reason": "job_error"}
