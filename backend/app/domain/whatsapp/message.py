"""
WhatsApp Message Contract — FASE 10

Internal message representation. WhatsApp messages are UNTRUSTED INPUT.
All fields come from the WhatsApp Service (TypeScript) and are validated.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class MessageType(str, Enum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
    UNKNOWN = "UNKNOWN"


class MessageDirection(str, Enum):
    INCOMING = "INCOMING"
    OUTGOING = "OUTGOING"


@dataclass
class WhatsAppMessage:
    """Normalized incoming WhatsApp message."""
    provider_message_id: str
    account_id: str
    sender_phone: str
    text: str
    message_type: MessageType = MessageType.TEXT
    timestamp: Optional[datetime] = None
    from_me: bool = False
    raw: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class WhatsAppOutbound:
    """Outbound message to send via WhatsApp Service."""
    recipient_phone: str
    text: str
    account_id: str
    idempotency_key: Optional[str] = None
    request_id: Optional[str] = None
