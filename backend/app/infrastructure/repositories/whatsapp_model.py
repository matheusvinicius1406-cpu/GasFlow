"""
WhatsApp SQLAlchemy Models — Modelos de persistência do WhatsApp.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.infrastructure.database.base import Base


class WhatsAppConversationModel(Base):
    __tablename__ = "whatsapp_conversations"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, index=True, nullable=False)
    client_codigo = Column(String, ForeignKey("clients.codigo"), nullable=True)
    status = Column(String, default="idle")
    last_message = Column(Text, nullable=True)
    last_message_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("WhatsAppMessageModel", back_populates="conversation")


class WhatsAppMessageModel(Base):
    __tablename__ = "whatsapp_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("whatsapp_conversations.id"), nullable=False)
    direction = Column(String, nullable=False)
    message_type = Column(String, default="text")
    content = Column(Text, nullable=True)
    raw_payload = Column(Text, nullable=True)
    status = Column(String, default="received")
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("WhatsAppConversationModel", back_populates="messages")
