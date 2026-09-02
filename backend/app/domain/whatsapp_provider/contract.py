"""
WhatsApp Provider Contract — WAVE 2

Abstract interface that all WhatsApp providers must implement.
The GasFlow domain depends ONLY on this contract.

Providers:
- WhatsAppWebProvider (current whatsapp-web.js)
- EvolutionProvider (Evolution API)
- BaileysProvider (Baileys — experimental)
- MetaProvider (Meta Cloud API — future)
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Callable, Awaitable
from app.domain.whatsapp_provider.models import (
    WhatsAppContact, WhatsAppMessage, WhatsAppMedia, ConnectionInfo,
    SendOptions, SendResult, WhatsAppEvent, ConnectionState, ProviderType,
)


class WhatsAppProvider(ABC):
    """Abstract WhatsApp provider contract.

    All providers must implement these methods.
    The GasFlow domain should ONLY use this interface.
    """

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        """Return the provider type identifier."""
        ...

    @property
    @abstractmethod
    def account_id(self) -> str:
        """Return the account ID this provider manages."""
        ...

    # ── Lifecycle ────────────────────────────────────────

    @abstractmethod
    async def start(self) -> None:
        """Start the provider and connect to WhatsApp."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the provider gracefully."""
        ...

    @abstractmethod
    async def logout(self) -> None:
        """Logout and destroy the session."""
        ...

    # ── Status ───────────────────────────────────────────

    @abstractmethod
    async def get_connection_state(self) -> ConnectionState:
        """Get current connection state."""
        ...

    @abstractmethod
    async def get_connection_info(self) -> ConnectionInfo:
        """Get detailed connection health info."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Quick check if provider is connected."""
        ...

    # ── QR Code ──────────────────────────────────────────

    @abstractmethod
    async def get_qr_code(self) -> Optional[str]:
        """Get current QR code for pairing. Returns None if not available."""
        ...

    # ── Messaging ────────────────────────────────────────

    @abstractmethod
    async def send_text(self, options: SendOptions) -> SendResult:
        """Send a text message."""
        ...

    @abstractmethod
    async def send_media(self, options: SendOptions) -> SendResult:
        """Send a media message (image, audio, document, etc)."""
        ...

    @abstractmethod
    async def send_typing(self, recipient: str) -> bool:
        """Send typing indicator."""
        ...

    @abstractmethod
    async def mark_as_read(self, message_id: str) -> bool:
        """Mark a message as read."""
        ...

    # ── Contacts ─────────────────────────────────────────

    @abstractmethod
    async def get_contacts(self) -> List[WhatsAppContact]:
        """Get all contacts."""
        ...

    @abstractmethod
    async def get_contact(self, jid: str) -> Optional[WhatsAppContact]:
        """Get a specific contact by JID."""
        ...

    # ── Session ──────────────────────────────────────────

    @abstractmethod
    async def get_session_info(self) -> Dict[str, Any]:
        """Get session metadata (phone, platform, etc)."""
        ...

    # ── Events ───────────────────────────────────────────

    def on_event(self, callback: Callable[[WhatsAppEvent], Awaitable[None]]) -> None:
        """Register an event callback. Default: no-op."""
        pass

    # ── Health ───────────────────────────────────────────

    async def health_check(self) -> bool:
        """Quick health check. Default: use connection state."""
        return self.is_connected()
