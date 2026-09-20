"""
Print Queue Service — F10.7

Fila de impressão persistida + claim pelo agente local (app desktop), que é
quem tem acesso USB à impressora.

Fluxo:
    pedido pago (ou botão Imprimir)
        → enqueue(): dados REAIS do pedido → ESC/POS → grava PENDING
    app desktop (poll)
        → claim_next(): reivindica o mais antigo (PENDING → PROCESSING)
        → imprime no spooler do Windows
        → complete(): COMPLETED (ou FAILED + motivo, elegível a reimpressão)

Idempotência do auto-print é do banco (existe job do pedido?), não de um dict
em memória — assim sobrevive a restart e a múltiplos workers.
"""

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.application.printing.receipt_data import build_receipt_data
from app.core.logging import setup_logging

# O estado do agente vive em app/core/printer_status.py (compartilhado entre
# workers); reexportado aqui para os call-sites que já importavam daqui.
from app.core.printer_status import get_agent_status, report_agent_status  # noqa: F401
from app.infrastructure.printing.escpos import ReceiptFormatter
from app.infrastructure.repositories.print_job_model import PrintJobModel

logger = setup_logging("INFO")

__all__ = ["PrintQueueService", "get_agent_status", "report_agent_status"]

# Marcador de quem criou o job por auto-impressão. É o discriminador CERTO de
# "ja imprimiu sozinho": `is_reprint=False` também vale para o botão Imprimir
# do operador, então usá-lo aqui fazia um cupom manual suprimir o automático
# (e o log mentia "already_auto_printed").
AUTO_PRINT_REQUESTER = "auto_print"

# Um job em PROCESSING que não foi concluído neste tempo é considerado órfão
# (app fechou no meio da impressão) e volta para a fila.
CLAIM_TIMEOUT_SECONDS = 120
MAX_ATTEMPTS = 5

# Dia do operador — o cupom só sai se for "de hoje".
#
# Sem isto, reabrir o app de manhã despejava no spooler a fila inteira de ontem
# (cupom de pedido já entregue, papel e atenção do operador jogados fora). A
# regra é o DIA LOCAL, não uma janela de horas: `created_at` é UTC, e a virada
# local (America/Sao_Paulo = UTC-3) é a que o operador enxerga.
#
# O que vence vira `EXPIRED` (visível na tela, com botão de reimprimir) em vez
# de sumir — e reimprimir cria um job NOVO, com carimbo de agora, que sai na
# hora.
DEFAULT_TZ = "America/Sao_Paulo"

# Fuso lido das settings a cada 60s (o claim roda a cada 3s; a setting não muda).
_TZ_CACHE_TTL_SECONDS = 60
_tz_cache: Dict[str, Tuple[float, str]] = {}


def _operator_timezone() -> str:
    """Fuso do operador: setting `timezone` (é a mesma que o resto do sistema usa).

    Falha aberta para o default conhecido: fuso errado atrasa/adia a virada do
    dia em algumas horas, enquanto uma exceção aqui pararia a impressão.
    """
    cached = _tz_cache.get("tz")
    now = time.time()
    if cached and (now - cached[0]) < _TZ_CACHE_TTL_SECONDS:
        return cached[1]
    name = DEFAULT_TZ
    try:
        from app.application.settings.settings_service import SettingsService
        from app.infrastructure.database.init_db import engine
        from sqlalchemy.orm import Session as _Session

        session = _Session(bind=engine)
        try:
            raw = SettingsService(session).get_value("timezone", DEFAULT_TZ)
        finally:
            session.close()
        if isinstance(raw, str) and raw.strip():
            name = raw.strip()
    except Exception:  # noqa: BLE001 — sem settings, o default serve
        name = DEFAULT_TZ
    _tz_cache["tz"] = (now, name)
    return name


def _start_of_local_day_utc(tz_name: str) -> datetime:
    """Meia-noite LOCAL de hoje convertida para UTC naive (formato de `created_at`)."""
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 — fuso inválido nas settings
        logger.warning("print_queue: fuso inválido '%s' — usando %s", tz_name, DEFAULT_TZ)
        tz = ZoneInfo(DEFAULT_TZ)
    start_local = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(timezone.utc).replace(tzinfo=None)


def _local_date(utc_naive: datetime, tz_name: str) -> Any:
    """Data local de um carimbo UTC naive (para "impressos hoje")."""
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tz = ZoneInfo(DEFAULT_TZ)
    return utc_naive.replace(tzinfo=timezone.utc).astimezone(tz).date()


class PrintQueueService:
    """Fila de impressão do tenant (persistida)."""

    def __init__(self, db: DBSession, tenant_id: str = "default"):
        self.db = db
        self.tenant_id = tenant_id
        self._formatter = ReceiptFormatter()

    def _tz(self) -> str:
        return _operator_timezone()

    # ── Enfileirar ─────────────────────────────────────────────

    def enqueue(
        self,
        order_id: str,
        requested_by: str = "",
        is_reprint: bool = False,
        order_data: Optional[Dict[str, Any]] = None,
    ) -> PrintJobModel:
        """Cria o job com o cupom já montado.

        `order_data` é montado a partir do pedido real quando não informado
        (caminho normal). Levanta `OrderNotFoundError` se o pedido não existe.
        """
        job, _created = self._insert(
            order_id=order_id,
            requested_by=requested_by,
            is_reprint=is_reprint,
            order_data=order_data,
        )
        return job

    def enqueue_auto(
        self,
        order_id: str,
        order_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[PrintJobModel, bool]:
        """Enfileira o cupom automático do pedido.

        Devolve `(job, criado_agora)`. `criado_agora=False` quando outro evento/
        worker venceu a corrida e o job devolvido é o dele — assim quem chamou
        reporta "já estava impresso" em vez de mentir "criei um job".
        """
        return self._insert(
            order_id=order_id,
            requested_by=AUTO_PRINT_REQUESTER,
            is_reprint=False,
            order_data=order_data,
        )

    def _insert(
        self,
        order_id: str,
        requested_by: str,
        is_reprint: bool,
        order_data: Optional[Dict[str, Any]],
    ) -> Tuple[PrintJobModel, bool]:
        """INSERT do job.

        A corrida no MESMO pedido (dois eventos, dois workers) é resolvida pelo
        banco: o índice único parcial `uq_print_jobs_auto_order` só aceita um
        job de auto-impressão por pedido, e quem perde o INSERT devolve o job
        do vencedor. Um lock de processo não valeria nada com
        BACKEND_WORKERS>1.
        """
        data = order_data or build_receipt_data(self.db, self.tenant_id, order_id)

        job = PrintJobModel(
            id=f"print-{order_id}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}",
            tenant_id=self.tenant_id,
            order_id=order_id,
            status="PENDING",
            is_reprint=is_reprint,
            requested_by=requested_by,
            attempts=0,
            payload=self._formatter.format_order(data),
        )
        self.db.add(job)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self._find_auto_job(order_id)
            if existing is None:
                raise
            logger.info(
                "print.enqueue_deduped",
                extra={"order_id": order_id, "job_id": existing.id},
            )
            return existing, False
        self.db.refresh(job)
        logger.info(
            "print.enqueued",
            extra={"job_id": job.id, "order_id": order_id, "reprint": is_reprint},
        )
        return job, True

    # ── Agente (app desktop) ───────────────────────────────────

    def claim_next(self) -> Optional[Tuple[PrintJobModel, bytes]]:
        """Reivindica o job mais antigo disponível para impressão.

        Devolve `(job, escpos_bytes)` ou None quando não há nada na fila.
        Jobs em PROCESSING presos (app caiu) voltam para PENDING após o
        timeout; jobs que estouraram as tentativas ficam FAILED.

        O claim é ATÔMICO: quem leva a linha é o UPDATE condicional (status
        ainda PENDING), não o SELECT. Dois agentes que leram o mesmo job —
        dois PCs, ou dois workers do backend — só imprimem um cupom: o perdedor
        recebe None e espera o próximo poll.
        """
        self._requeue_stale()
        self.expire_previous_days()

        candidate = self._peek_next()
        if candidate is None:
            return None

        job_id = candidate.id
        if int(candidate.attempts or 0) >= MAX_ATTEMPTS:
            self._mark_failed(job_id, f"máximo de tentativas ({MAX_ATTEMPTS}) excedido")
            logger.warning("print.gave_up", extra={"job_id": job_id, "order_id": candidate.order_id})
            return None

        if not self._claim(job_id):
            # Outro agente levou a linha entre o SELECT e o UPDATE.
            logger.info("print.claim_lost_race", extra={"job_id": job_id})
            return None

        job = self.get_job(job_id)
        if job is None:
            return None
        return job, bytes(job.payload or b"")

    def _peek_next(self) -> Optional[PrintJobModel]:
        """Lê o PENDING mais antigo — leitura pura, não reivindica nada."""
        return (
            self.db.query(PrintJobModel)
            .filter(
                PrintJobModel.tenant_id == self.tenant_id,
                PrintJobModel.status == "PENDING",
            )
            .order_by(PrintJobModel.created_at)
            .first()
        )

    def _claim(self, job_id: str) -> bool:
        """UPDATE condicional: True apenas para quem levou a linha.

        O `status == PENDING` no WHERE é o que impede dois agentes de
        imprimirem o mesmo cupom — o SELECT não decide nada, este UPDATE sim.
        """
        claimed = (
            self.db.query(PrintJobModel)
            .filter(
                PrintJobModel.id == job_id,
                PrintJobModel.tenant_id == self.tenant_id,
                PrintJobModel.status == "PENDING",
            )
            .update(
                {
                    PrintJobModel.status: "PROCESSING",
                    PrintJobModel.claimed_at: datetime.utcnow(),
                    PrintJobModel.attempts: PrintJobModel.attempts + 1,
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        return claimed == 1

    def _mark_failed(self, job_id: str, error: str) -> None:
        """Marca o job como FAILED (só se ainda estiver na fila)."""
        self.db.query(PrintJobModel).filter(
            PrintJobModel.id == job_id,
            PrintJobModel.tenant_id == self.tenant_id,
            PrintJobModel.status == "PENDING",
        ).update(
            {
                PrintJobModel.status: "FAILED",
                PrintJobModel.error: error,
                PrintJobModel.completed_at: datetime.utcnow(),
            },
            synchronize_session=False,
        )
        self.db.commit()

    def complete(
        self,
        job_id: str,
        success: bool,
        error: str = "",
        printer_name: Optional[str] = None,
    ) -> Optional[PrintJobModel]:
        """Resultado do agente: COMPLETED ou FAILED (com motivo)."""
        job = (
            self.db.query(PrintJobModel)
            .filter(PrintJobModel.id == job_id, PrintJobModel.tenant_id == self.tenant_id)
            .first()
        )
        if job is None:
            return None

        job.status = "COMPLETED" if success else "FAILED"
        job.error = None if success else (error or "falha ao imprimir")[:500]
        job.printer_name = printer_name or job.printer_name
        job.completed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(job)
        level = logger.info if success else logger.warning
        level(
            "print.completed" if success else "print.failed",
            extra={"job_id": job.id, "order_id": job.order_id, "printer": job.printer_name},
        )
        return job

    def expire_previous_days(self) -> int:
        """Vence o que ficou de dias anteriores — não sai sozinho ao reabrir o app.

        Devolve quantos venceu. Idempotente (rodar de novo não acha nada). O job
        NÃO é apagado: vira `EXPIRED` com o motivo, porque o operador precisa ver
        que ficou sem cupom (e reimprimir com um clique, o que cria um job novo).
        """
        cutoff = _start_of_local_day_utc(self._tz())
        old = (
            self.db.query(PrintJobModel)
            .filter(
                PrintJobModel.tenant_id == self.tenant_id,
                PrintJobModel.status == "PENDING",
                PrintJobModel.created_at < cutoff,
            )
            .all()
        )
        if not old:
            return 0
        now = datetime.utcnow()
        for job in old:
            job.status = "EXPIRED"
            job.error = "cupom de dia anterior — não sai sozinho; reimprima se precisar"
            job.completed_at = now
        self.db.commit()
        logger.info("print.expired_old_jobs", extra={"count": len(old)})
        return len(old)

    def _requeue_stale(self) -> None:
        cutoff = datetime.utcnow() - timedelta(seconds=CLAIM_TIMEOUT_SECONDS)
        stale = (
            self.db.query(PrintJobModel)
            .filter(
                PrintJobModel.tenant_id == self.tenant_id,
                PrintJobModel.status == "PROCESSING",
                PrintJobModel.claimed_at < cutoff,
            )
            .all()
        )
        if not stale:
            return
        for job in stale:
            job.status = "PENDING"
            job.error = "reivindicação expirou — devolvido à fila"
        self.db.commit()
        logger.warning("print.requeued_stale", extra={"count": len(stale)})

    # ── Consultas ──────────────────────────────────────────────

    def expired_count(self) -> int:
        """Quantos cupons venceram (o agente usa para avisar o operador).

        `count()` e não `queue_counts()`: isto roda no poll de 3s do agente, não
        vale varrer a tabela inteira para saber um número.
        """
        return (
            self.db.query(PrintJobModel)
            .filter(
                PrintJobModel.tenant_id == self.tenant_id,
                PrintJobModel.status == "EXPIRED",
            )
            .count()
        )

    def list_jobs(self, limit: int = 50) -> List[PrintJobModel]:
        return (
            self.db.query(PrintJobModel)
            .filter(PrintJobModel.tenant_id == self.tenant_id)
            .order_by(PrintJobModel.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_job(self, job_id: str) -> Optional[PrintJobModel]:
        return (
            self.db.query(PrintJobModel)
            .filter(PrintJobModel.id == job_id, PrintJobModel.tenant_id == self.tenant_id)
            .first()
        )

    def jobs_for_order(self, order_id: str) -> List[PrintJobModel]:
        return (
            self.db.query(PrintJobModel)
            .filter(PrintJobModel.tenant_id == self.tenant_id, PrintJobModel.order_id == order_id)
            .order_by(PrintJobModel.created_at.desc())
            .all()
        )

    def has_job_for_order(self, order_id: str, only_auto: bool = True) -> bool:
        """Idempotência: já existe job deste pedido?

        `only_auto=True` conta **apenas** o job criado pelo auto-print
        (`requested_by=AUTO_PRINT_REQUESTER`) — reimpressão manual do operador
        (`is_reprint=True`) e impressão manual de um pedido novo
        (`is_reprint=False`, botão Imprimir) não são marca de auto-impressão,
        e antes a segunda era: o pedido pago deixava de imprimir sozinho.
        """
        if only_auto:
            return self._find_auto_job(order_id) is not None
        return (
            self.db.query(PrintJobModel)
            .filter(
                PrintJobModel.tenant_id == self.tenant_id,
                PrintJobModel.order_id == order_id,
            )
            .first()
            is not None
        )

    def _find_auto_job(self, order_id: str) -> Optional[PrintJobModel]:
        """Job de auto-impressão do pedido (no máximo um, por índice único)."""
        return (
            self.db.query(PrintJobModel)
            .filter(
                PrintJobModel.tenant_id == self.tenant_id,
                PrintJobModel.order_id == order_id,
                PrintJobModel.requested_by == AUTO_PRINT_REQUESTER,
                PrintJobModel.is_reprint.is_(False),
            )
            .order_by(PrintJobModel.created_at)
            .first()
        )

    def queue_counts(self) -> Dict[str, int]:
        """Contadores da fila (a UI mostra fila/falhas/vencidos/impressos hoje)."""
        tz = self._tz()
        today = _local_date(datetime.utcnow(), tz)
        jobs = self.db.query(PrintJobModel).filter(PrintJobModel.tenant_id == self.tenant_id).all()
        return {
            "pending": sum(1 for j in jobs if j.status in ("PENDING", "PROCESSING")),
            "failed": sum(1 for j in jobs if j.status == "FAILED"),
            # Vencido é cupom que o operador não recebeu: conta para atenção.
            "expired": sum(1 for j in jobs if j.status == "EXPIRED"),
            "completed_today": sum(
                1
                for j in jobs
                if j.status == "COMPLETED" and j.completed_at and _local_date(j.completed_at, tz) == today
            ),
        }
