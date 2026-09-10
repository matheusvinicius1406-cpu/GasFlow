"""
Normalized WhatsApp Models — WAVE 2

Provider-independent models that abstract differences between
the embedded Baileys service, Evolution API, and Meta Cloud API.
(Histórico: o motor original era whatsapp-web.js — substituído por Baileys.)

The GasFlow domain should ONLY use these models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class ConnectionState(str, Enum):
    """Normalized connection states across all providers."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    QR_PENDING = "qr_pending"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    AUTH_FAILED = "auth_failed"


class MessageStatus(str, Enum):
    """Normalized message delivery status."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class MediaType(str, Enum):
    """Normalized media types."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    STICKER = "sticker"
    LOCATION = "location"


class ProviderType(str, Enum):
    """Supported provider types."""

    CURRENT = "current"  # serviço local embutido (Baileys) via HTTP
    EVOLUTION = "evolution"  # Evolution API
    BAILEYS = "baileys"  # Baileys
    META = "meta"  # Meta Cloud API (future)


@dataclass
class WhatsAppContact:
    """Normalized contact — same structure for all providers."""

    jid: str
    phone: Optional[str] = None
    name: Optional[str] = None
    push_name: Optional[str] = None
    business_name: Optional[str] = None
    is_business: bool = False
    is_group: bool = False

    def to_dict(self) -> dict:
        return {
            "jid": self.jid,
            "phone": self.phone,
            "name": self.name,
            "push_name": self.push_name,
            "business_name": self.business_name,
            "is_business": self.is_business,
            "is_group": self.is_group,
        }


@dataclass
class WhatsAppMessage:
    """Normalized message — provider-independent."""

    id: str
    provider_message_id: str
    account_id: str
    sender_jid: str
    recipient_jid: str
    text: str = ""
    media_type: MediaType = MediaType.TEXT
    status: MessageStatus = MessageStatus.PENDING
    timestamp: Optional[datetime] = None
    from_me: bool = False
    raw: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "provider_message_id": self.provider_message_id,
            "account_id": self.account_id,
            "sender_jid": self.sender_jid,
            "recipient_jid": self.recipient_jid,
            "text": self.text,
            "media_type": self.media_type.value,
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "from_me": self.from_me,
        }


@dataclass
class WhatsAppMedia:
    """Normalized media attachment."""

    url: Optional[str] = None
    mimetype: Optional[str] = None
    filename: Optional[str] = None
    size: Optional[int] = None
    data: Optional[bytes] = None  # For inline media


@dataclass
class ConnectionInfo:
    """Normalized connection health info."""

    connected: bool = False
    authenticated: bool = False
    ready: bool = False
    phone: Optional[str] = None
    latency_ms: Optional[float] = None
    last_event_at: Optional[datetime] = None
    last_send_at: Optional[datetime] = None
    last_error: Optional[str] = None
    provider_type: ProviderType = ProviderType.CURRENT

    def to_dict(self) -> dict:
        return {
            "connected": self.connected,
            "authenticated": self.authenticated,
            "ready": self.ready,
            "phone": self.phone,
            "latency_ms": self.latency_ms,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
            "last_send_at": self.last_send_at.isoformat() if self.last_send_at else None,
            "last_error": self.last_error,
            "provider_type": self.provider_type.value,
        }


@dataclass
class SendOptions:
    """Options for sending a message."""

    recipient: str
    text: str = ""
    media: Optional[WhatsAppMedia] = None
    media_type: MediaType = MediaType.TEXT
    account_id: str = "primary"
    idempotency_key: Optional[str] = None
    reply_to: Optional[str] = None


@dataclass
class SendResult:
    """Result of sending a message."""

    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    provider: Optional[ProviderType] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message_id": self.message_id,
            "error": self.error,
            "error_code": self.error_code,
            "provider": self.provider.value if self.provider else None,
        }


# ── Normalized Events ──────────────────────────────────


@dataclass
class WhatsAppEvent:
    """Normalized event from any provider."""

    event_type: str  # message.received, message.status, connection.changed, etc.
    account_id: str
    provider_type: ProviderType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "account_id": self.account_id,
            "provider_type": self.provider_type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
