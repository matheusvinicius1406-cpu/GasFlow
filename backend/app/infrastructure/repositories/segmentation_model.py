"""
Segmentation SQLAlchemy Model — FASE 13.1

Persists segments and their rules to database.
Rules are stored as JSON for flexibility.
Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class SegmentModel(Base):
    __tablename__ = "segments"

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON array of rules
    rule_logic: Mapped[Optional[str]] = mapped_column(String(10), default="AND")  # AND or OR
    status: Mapped[Optional[str]] = mapped_column(String(20), default="DRAFT")  # DRAFT, ACTIVE, ARCHIVED
    member_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    last_evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_segments_status", "status"),
        Index("ix_segments_tenant_status", "tenant_id", "status"),
    )
