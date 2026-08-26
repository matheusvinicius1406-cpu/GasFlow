"""
WhatsApp Schemas — Schemas Pydantic para request/response da API de WhatsApp.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class WhatsAppConversationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    phone_number: str
    client_codigo: Optional[str] = None
    status: str
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WhatsAppMessageResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    conversation_id: int
    direction: str
    message_type: str
    content: Optional[str] = None
    status: str
    created_at: datetime


class WhatsAppSendRequest(BaseModel):
    phone_number: str
    message: str


class WhatsAppSendResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None
