"""
WhatsApp SQLAlchemy Models — FASE 10

Extended models supporting:
- Multi-account isolation
- Conversation state machine
- Order draft persistence
- Message idempotency

Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic e os relacionamentos ganham anotação.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class WhatsAppConversationModel(Base):
    __tablename__ = "whatsapp_conversations"

    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default", index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[str] = mapped_column(String(50), nullable=False, default="primary", index=True)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    client_codigo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    status: Mapped[Optional[str]] = mapped_column(
        String(30), default="IDLE"
    )  # IDLE, BROWSING, BUILDING_ORDER, AWAITING_CONFIRMATION, ORDER_CREATED, HUMAN_PENDING, HUMAN_ACTIVE, CLOSED
    human_operator: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    draft_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-serialized order draft
    last_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages: Mapped[list["WhatsAppMessageModel"]] = relationship("WhatsAppMessageModel", back_populates="conversation")

    __table_args__ = (
        # Unicidade por tenant: duas empresas podem ter conversa com o mesmo
        # telefone (P0 multiempresa — migração c1a2b3d4e5f6).
        UniqueConstraint("tenant_id", "account_id", "phone_number", name="uq_wa_conversation_tenant_account_phone"),
        Index("ix_wa_conversation_status", "status"),
    )


class WhatsAppMessageModel(Base):
    __tablename__ = "whatsapp_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("whatsapp_conversations.id"), nullable=False, index=True
    )
    provider_message_id: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, unique=True
    )  # Idempotency key
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # INCOMING / OUTGOING
    sender: Mapped[str] = mapped_column(
        String(20), nullable=False, default="customer"
    )  # customer / assistant / system / human
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    message_type: Mapped[Optional[str]] = mapped_column(String(20), default="TEXT")
    status: Mapped[Optional[str]] = mapped_column(String(20), default="received")
    raw_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped["WhatsAppConversationModel"] = relationship(
        "WhatsAppConversationModel", back_populates="messages"
    )

    __table_args__ = (Index("ix_wa_message_conversation_created", "conversation_id", "created_at"),)
