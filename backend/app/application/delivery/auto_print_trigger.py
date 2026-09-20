"""
Auto-print trigger — F3 / F10.7

Quando um pedido entra em um dos status configurados (setting
`printer.auto_print.min_status`, default "PAID,CONFIRMED"), um job de
impressão é criado UMA única vez.

Mudança da F10.7: a idempotência saiu da memória e foi para o banco. Antes o
registro de "já auto-impresso" era um `dict` do processo — um restart do
backend fazia o mesmo pedido ser auto-impresso de novo, e o dict nem sequer
sobrevivia. Agora vale "existe job de auto-impressão deste pedido?" e quem
fecha a corrida entre dois workers é o índice único parcial
`uq_print_jobs_auto_order` — a checagem em Python é só o caminho barato.

Falha transitória ao ENFILEIRAR (pedido inexistente, banco fora) não cria
linha nenhuma, então o próximo evento tenta de novo. Um job que já existe mas
FALHOU na impressora não é reenfileirado automaticamente — o operador vê a
falha na tela de impressão e reimprime (rosto visível em vez de loop mudo).
"""

import threading
from typing import Any, Dict, Optional

from app.core.logging import setup_logging
from sqlalchemy.orm import Session as DBSession

logger = setup_logging("INFO")

# Lock curto POR PROCESSO: evita duas sessões concorrentes para o mesmo pedido
# dentro deste worker. Não é a garantia — com BACKEND_WORKERS>1 (default em
# prod) a corrida é real. Quem a fecha é o índice único parcial
# `uq_print_jobs_auto_order` (print_jobs), tratado no PrintQueueService._insert
# (IntegrityError → devolve o job do vencedor).
_enqueue_lock = threading.Lock()


class AutoPrintTrigger:
    """Cria print jobs automaticamente para pedidos em status elegíveis."""

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

    # ── Idempotência (banco) ───────────────────────────────────

    def already_printed(self, order_id: str, tenant_id: str = "default", db: Optional[DBSession] = None) -> bool:
        """Já existe job de auto-impressão deste pedido?"""
        own = db is None
        session = db or self._open_session()
        try:
            from app.application.printing.print_queue import PrintQueueService

            return PrintQueueService(session, tenant_id).has_job_for_order(order_id, only_auto=True)
        except Exception:
            logger.warning("auto_print_idempotency_lookup_failed", extra={"order_id": order_id})
            return True  # conservador: na dúvida, não imprime de novo
        finally:
            if own:
                session.close()

    # ── Trigger principal ──────────────────────────────────────

    def maybe_auto_print(
        self,
        order_id: str,
        tenant_id: str,
        order_status: str,
        order_data: Optional[Dict[str, Any]] = None,
        db: Optional[DBSession] = None,
    ) -> Dict[str, Any]:
        """Avalia se o pedido deve ser impresso agora.

        Regras:
        - status precisa estar em printer.auto_print.min_status
        - 1 job por pedido (idempotente em eventos repetidos)
        - retorno explica a decisão (skipped_reason) para auditoria
        """
        allowed = self._load_allowed_statuses()
        status = (order_status or "").upper()
        if status not in allowed:
            reason = f"status_not_eligible:{status or 'EMPTY'}"
            logger.info("auto_print.skipped", extra={"order_id": order_id, "reason": reason})
            return {"created": False, "skipped_reason": reason}

        own = db is None
        session = db or self._open_session()
        try:
            from app.application.printing.print_queue import PrintQueueService

            queue = PrintQueueService(session, tenant_id)
            with _enqueue_lock:
                if queue.has_job_for_order(order_id, only_auto=True):
                    return {"created": False, "skipped_reason": "already_auto_printed"}
                job, created = queue.enqueue_auto(order_id=order_id, order_data=order_data)
            if not created:
                # Outro worker/evento venceu a corrida entre a checagem e o
                # INSERT — o cupom já está na fila (um só, garantido pelo
                # índice). Reportar "criei" aqui seria mentira no log.
                logger.info(
                    "auto_print.raced",
                    extra={"order_id": order_id, "job_id": job.id},
                )
                return {
                    "created": False,
                    "skipped_reason": "already_auto_printed",
                    "job_id": job.id,
                }
            logger.info("auto_print.job_created", extra={"order_id": order_id, "job_id": job.id})
            return {"created": True, "job_id": job.id}
        except Exception:
            # Nada foi criado → o próximo evento deste pedido tenta de novo.
            logger.exception("auto_print.job_failed", extra={"order_id": order_id})
            return {"created": False, "skipped_reason": "job_error"}
        finally:
            if own:
                session.close()

    # ── Infra ──────────────────────────────────────────────────

    @staticmethod
    def _open_session() -> DBSession:
        from app.infrastructure.database.init_db import engine

        return DBSession(bind=engine)
