"""
AI SQLAlchemy Models — FASE 9
"""

from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from app.infrastructure.database.base import Base


class ConversationModel(Base):
    __tablename__ = "ai_conversations"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(36), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AIMessageModel(Base):
    __tablename__ = "ai_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(36), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, system, tool_call, tool_result
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)  # JSON string for extra data
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AIAuditLogModel(Base):
    __tablename__ = "ai_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(32), nullable=False, index=True)
    conversation_id = Column(String(36), nullable=True)
    intent = Column(String(50), nullable=True)
    tool = Column(String(50), nullable=True)
    confidence = Column(String(10), nullable=True)
    success = Column(Integer, nullable=True)  # 1=success, 0=failure
    latency_ms = Column(Integer, nullable=True)
    model = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
