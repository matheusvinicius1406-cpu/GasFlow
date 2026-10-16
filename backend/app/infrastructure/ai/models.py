"""
AI SQLAlchemy Models — FASE 9
Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class ConversationModel(Base):
    __tablename__ = "ai_conversations"

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    external_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AIMessageModel(Base):
    __tablename__ = "ai_messages"

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system, tool_call, tool_result
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string for extra data
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AIAuditLogModel(Base):
    __tablename__ = "ai_audit_log"

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    request_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tool: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    success: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1=success, 0=failure
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
