from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, func


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    """Colunas de auditoria com timezone. Reutilizável por todos os modelos."""

    created_at = Column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )
