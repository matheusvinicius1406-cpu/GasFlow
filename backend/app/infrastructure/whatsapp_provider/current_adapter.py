"""
Current WhatsApp Provider Adapter — WAVE 2

Wraps the existing whatsapp-web.js Node.js service via HTTP API.
This adapter preserves all current behavior while conforming to the new contract.

Architecture:
FastAPI → WhatsAppWebAdapter → HTTP → Node.js /whatsapp/* → whatsapp-web.js → WhatsApp
"""

import httpx
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.domain.whatsapp_provider.contract import WhatsAppProvider
from app.domain.whatsapp_provider.models import (
    WhatsAppContact, ConnectionInfo, SendOptions, SendResult,
    ConnectionState, ProviderType,
)
from app.domain.whatsapp_provider.errors import (
    WhatsAppConnectionError,
)

logger = logging.getLogger("gasflow.whatsapp.current")

# Default Node.js service URL
DEFAULT_SERVICE_URL = "http://localhost:3000"
SEND_TIMEOUT = 30
DEFAULT_TIMEOUT = 10


class WhatsAppWebAdapter(WhatsAppProvider):
    """Adapter for the current whatsapp-web.js Node.js service."""

    def __init__(self, account_id: str, service_url: str = DEFAULT_SERVICE_URL):
        self._account_id = account_id
        self._service_url = service_url.rstrip("/") + "/api"
        self._connected = False
        self._phone: Optional[str] = None
        self._last_connected_at: Optional[datetime] = None
        self._last_event_at: Optional[datetime] = None
        self._last_send_at: Optional[datetime] = None
        self._last_error: Optional[str] = None

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.CURRENT

    @property
    def account_id(self) -> str:
        return self._account_id

    # ── Lifecycle ────────────────────────────────────────

    async def start(self) -> None:
        """Start is handled by the Node.js service. This just verifies connection."""
        try:
            info = await self._get_account_status()
            if info and info.get("connected"):
                self._connected = True
                self._phone = info.get("phone")
                self._last_connected_at = datetime.utcnow()
            else:
                self._connected = False
        except Exception as e:
            self._connected = False
            self._last_error = str(e)
            raise WhatsAppConnectionError(
                f"Cannot connect to WhatsApp service: {e}",
                provider="current",
            )

    async def stop(self) -> None:
        """Stop is handled by the Node.js service."""
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                await client.post(f"{self._service_url}/disconnect/{self._account_id}")
            self._connected = False
        except Exception as e:
            logger.warning(f"[current] Error stopping: {e}")

    async def logout(self) -> None:
        """Logout via Node.js service."""
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                await client.post(f"{self._service_url}/logout/{self._account_id}")
            self._connected = False
            self._phone = None
        except Exception as e:
            logger.warning(f"[current] Error logging out: {e}")

    # ── Status ───────────────────────────────────────────

    async def get_connection_state(self) -> ConnectionState:
        try:
            info = await self._get_account_status()
            if not info:
                return ConnectionState.DISCONNECTED
            state = info.get("state", "disconnected")
            mapping = {
                "connected": ConnectionState.CONNECTED,
                "connecting": ConnectionState.CONNECTING,
                "qr_pending": ConnectionState.QR_PENDING,
                "disconnected": ConnectionState.DISCONNECTED,
            }
            return mapping.get(state, ConnectionState.DISCONNECTED)
        except Exception:
            return ConnectionState.DISCONNECTED

    async def get_connection_info(self) -> ConnectionInfo:
        try:
            info = await self._get_account_status()
            if not info:
                return ConnectionInfo(provider_type=self.provider_type)
            return ConnectionInfo(
                connected=info.get("connected", False),
                authenticated=info.get("connected", False),
                ready=info.get("connected", False),
                phone=info.get("phone"),
                last_event_at=self._last_event_at,
                last_send_at=self._last_send_at,
                last_error=self._last_error,
                provider_type=self.provider_type,
            )
        except Exception as e:
            return ConnectionInfo(
                last_error=str(e),
                provider_type=self.provider_type,
            )

    def is_connected(self) -> bool:
        return self._connected

    # ── QR Code ──────────────────────────────────────────

    async def get_qr_code(self) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(f"{self._service_url}/qr/{self._account_id}")
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("qr")
        except Exception:
            pass
        return None

    # ── Messaging ────────────────────────────────────────

    async def send_text(self, options: SendOptions) -> SendResult:
        if not self._connected:
            return SendResult(
                success=False,
                error="WhatsApp not connected",
                error_code="NOT_CONNECTED",
                provider=self.provider_type,
            )

        try:
            async with httpx.AsyncClient(timeout=SEND_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._service_url}/send",
                    json={
                        "accountId": self._account_id,
                        "recipient": options.recipient,
                        "text": options.text,
                        "idempotencyKey": options.idempotency_key,
                    },
                )

                self._last_send_at = datetime.utcnow()

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        return SendResult(
                            success=True,
                            message_id=data.get("messageId"),
                            provider=self.provider_type,
                        )
                    else:
                        return SendResult(
                            success=False,
                            error=data.get("error", "Unknown error"),
                            provider=self.provider_type,
                        )
                else:
                    return SendResult(
                        success=False,
                        error=f"HTTP {resp.status_code}",
                        provider=self.provider_type,
                    )
        except httpx.TimeoutException:
            self._last_error = "Timeout"
            return SendResult(
                success=False,
                error="Timeout sending message",
                error_code="TIMEOUT",
                provider=self.provider_type,
            )
        except Exception as e:
            self._last_error = str(e)
            return SendResult(
                success=False,
                error=str(e),
                provider=self.provider_type,
            )

    async def send_media(self, options: SendOptions) -> SendResult:
        # Current provider doesn't support media via HTTP API yet
        return SendResult(
            success=False,
            error="Media send not yet supported via adapter",
            error_code="MEDIA_NOT_SUPPORTED",
            provider=self.provider_type,
        )

    async def send_typing(self, recipient: str) -> bool:
        # Current provider doesn't support typing indicator via HTTP API
        return False

    async def mark_as_read(self, message_id: str) -> bool:
        # Current provider doesn't support mark as read via HTTP API
        return False

    # ── Contacts ─────────────────────────────────────────

    async def get_contacts(self) -> List[WhatsAppContact]:
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(f"{self._service_url}/contacts/{self._account_id}")
                if resp.status_code == 200:
                    data = resp.json()
                    contacts = data.get("contacts", [])
                    return [
                        WhatsAppContact(
                            jid=c.get("jid", ""),
                            phone=c.get("phone"),
                            name=c.get("name"),
                            push_name=c.get("pushName"),
                            business_name=c.get("businessName"),
                            is_business=c.get("isBusiness", False),
                            is_group=c.get("isGroup", False),
                        )
                        for c in contacts
                    ]
        except Exception as e:
            logger.warning(f"[current] Error getting contacts: {e}")
        return []

    async def get_contact(self, jid: str) -> Optional[WhatsAppContact]:
        contacts = await self.get_contacts()
        for c in contacts:
            if c.jid == jid:
                return c
        return None

    # ── Session ──────────────────────────────────────────

    async def get_session_info(self) -> Dict[str, Any]:
        return {
            "account_id": self._account_id,
            "provider": "current",
            "phone": self._phone,
            "connected": self._connected,
            "last_connected_at": self._last_connected_at.isoformat() if self._last_connected_at else None,
        }

    # ── Health ───────────────────────────────────────────

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._service_url.replace('/api', '')}/api/health")
                if resp.status_code == 200:
                    data = resp.json()
                    accounts = data.get("whatsapp", {}).get("accounts", [])
                    for acc in accounts:
                        if acc.get("id") == self._account_id:
                            return acc.get("status", {}).get("connected", False)
        except Exception:
            pass
        return False

    # ── Private helpers ──────────────────────────────────

    async def _get_account_status(self) -> Optional[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(f"{self._service_url}/whatsapp/accounts")
                if resp.status_code == 200:
                    data = resp.json()
                    accounts = data.get("accounts", [])
                    for acc in accounts:
                        if acc.get("id") == self._account_id:
                            return acc
        except Exception as e:
            self._last_error = str(e)
        return None
