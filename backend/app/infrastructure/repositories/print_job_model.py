"""
Print job SQLAlchemy Model — F10.7 (fila de impressão persistida)

Antes a fila vivia num `dict` do processo (`PrintAgent._jobs`): um restart do
backend perdia os cupons pendentes (pedido pago podia nunca imprimir) e o
job ficava PENDING para sempre porque nada o reivindicava.

Aqui o job é persistido com o payload ESC/POS pronto, para o agente de
impressão (app desktop, que tem acesso USB à impressora) apenas pegar e
enviar.

Estilo SQLAlchemy 2.0 tipado (Mapped[...]) — mesmo padrão da F9.1.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, LargeBinary, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base

# Quem criou o job por auto-impressão (espelha AUTO_PRINT_REQUESTER do
# PrintQueueService — aqui em SQL para o índice parcial).
_AUTO_PRINT_REQUESTER = "auto_print"


class PrintJobModel(Base):
    __tablename__ = "print_jobs"

    # Índice único PARCIAL: no máximo UM job de auto-impressão por pedido.
    #
    # A idempotência do auto-print era um "já existe?" em Python — check-then-
    # insert, que dois workers (BACKEND_WORKERS=2 em prod) atravessam e criam
    # dois cupons do mesmo pedido. Parcial para NÃO bloquear o que é legítimo:
    # impressão manual do operador e reimpressão ficam fora do índice.
    __table_args__ = (
        Index(
            "uq_print_jobs_auto_order",
            "tenant_id",
            "order_id",
            unique=True,
            sqlite_where=text(f"requested_by = '{_AUTO_PRINT_REQUESTER}'"),
            postgresql_where=text(f"requested_by = '{_AUTO_PRINT_REQUESTER}'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, default="default", index=True, nullable=False)
    order_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # PENDING → PROCESSING → COMPLETED | FAILED
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    is_reprint: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # ESC/POS pronto (80mm) — o agente só transporta os bytes.
    payload: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    # Impressora que executou (auditoria: trocou de impressora, o que saiu onde?)
    printer_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def to_dict(self, include_payload: bool = False) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "order_id": self.order_id,
            "tenant_id": self.tenant_id,
            "status": self.status,
            "is_reprint": bool(self.is_reprint),
            "requested_by": self.requested_by or "",
            "attempts": int(self.attempts or 0),
            "error": self.error,
            "printer_name": self.printer_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_payload:
            out["payload_size"] = len(self.payload or b"")
        return out
