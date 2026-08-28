"""
WhatsApp SQLAlchemy Models — FASE 10

Extended models supporting:
- Multi-account isolation
- Conversation state machine
- Order draft persistence
- Message idempotency
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.infrastructure.database.base import Base


class WhatsAppConversationModel(Base):
    __tablename__ = "whatsapp_conversations"

    tenant_id = Column(String, default="default", index=True)
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String(50), nullable=False, default="primary", index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    client_codigo = Column(String(20), ForeignKey("clients.codigo"), nullable=True, index=True)
    status = Column(String(30), default="IDLE")  # IDLE, BROWSING, BUILDING_ORDER, AWAITING_CONFIRMATION, ORDER_CREATED, HUMAN_PENDING, HUMAN_ACTIVE, CLOSED
    human_operator = Column(String(100), nullable=True)
    draft_json = Column(Text, nullable=True)  # JSON-serialized order draft
    last_message = Column(Text, nullable=True)
    last_message_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("WhatsAppMessageModel", back_populates="conversation")

    __table_args__ = (
        UniqueConstraint("account_id", "phone_number", name="uq_wa_conversation_account_phone"),
        Index("ix_wa_conversation_status", "status"),
    )


class WhatsAppMessageModel(Base):
    __tablename__ = "whatsapp_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("whatsapp_conversations.id"), nullable=False, index=True)
    provider_message_id = Column(String(200), nullable=True, unique=True)  # Idempotency key
    direction = Column(String(10), nullable=False)  # INCOMING / OUTGOING
    sender = Column(String(20), nullable=False, default="customer")  # customer / assistant / system / human
    content = Column(Text, nullable=True)
    message_type = Column(String(20), default="TEXT")
    status = Column(String(20), default="received")
    raw_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("WhatsAppConversationModel", back_populates="messages")

    __table_args__ = (
        Index("ix_wa_message_conversation_created", "conversation_id", "created_at"),
    )
