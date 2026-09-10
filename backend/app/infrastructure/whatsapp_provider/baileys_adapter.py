"""
Baileys Provider Adapter — WAVE 2 (EXPERIMENTAL)

Adapter for Baileys (https://github.com/WhiskeySockets/Baileys).
Custom license — verify terms before commercial use.

This adapter communicates with a Baileys-based Node.js service
(not yet implemented — this is a structural placeholder).

Architecture:
FastAPI → BaileysAdapter → HTTP → Baileys Service → WhatsApp Web (WebSocket)
"""

import httpx
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.domain.whatsapp_provider.contract import WhatsAppProvider
from app.domain.whatsapp_provider.models import (
    WhatsAppContact,
    ConnectionInfo,
    SendOptions,
    SendResult,
    ConnectionState,
    ProviderType,
)
from app.domain.whatsapp_provider.errors import (
    WhatsAppConnectionError,
)

logger = logging.getLogger("gasflow.whatsapp.baileys")

DEFAULT_TIMEOUT = 10
SEND_TIMEOUT = 30


class BaileysAdapter(WhatsAppProvider):
    """Experimental adapter for Baileys.

    NOTE: This is a structural placeholder. A Baileys-based Node.js service
    would need to be built to make this functional.

    Baileys advantages over the previous whatsapp-web.js engine (histórico):
    - No Chromium/Puppeteer required (pure WebSocket)
    - Lower memory footprint (~50-100MB vs ~200-500MB)
    - Faster startup
    - Direct WebSocket connection

    License: Custom (Copyright 2025 Rajeh Taher/WhiskeySockets)
    Verify terms before commercial use.
    """

    def __init__(
        self,
        account_id: str,
        service_url: str = "http://localhost:3001",
    ):
        self._account_id = account_id
        self._service_url = service_url.rstrip("/")
        self._connected = False
        self._phone: Optional[str] = None
        self._last_connected_at: Optional[datetime] = None
        self._last_send_at: Optional[datetime] = None
        self._last_error: Optional[str] = None

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.BAILEYS

    @property
    def account_id(self) -> str:
        return self._account_id

    # ── Lifecycle ────────────────────────────────────────

    async def start(self) -> None:
        """Start Baileys session."""
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._service_url}/session/start",
                    json={"accountId": self._account_id},
                )
                if resp.status_code == 200:
                    self._connected = True
                    self._last_connected_at = datetime.utcnow()
                else:
                    raise Exception(f"HTTP {resp.status_code}")
        except httpx.ConnectError:
            self._connected = False
            raise WhatsAppConnectionError(
                "Baileys service not available. " "A Baileys-based Node.js service needs to be built.",
                provider="baileys",
            )
        except Exception as e:
            self._connected = False
            self._last_error = str(e)
            raise WhatsAppConnectionError(
                f"Baileys connection failed: {e}",
                provider="baileys",
            )

    async def stop(self) -> None:
        """Stop Baileys session."""
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                await client.post(
                    f"{self._service_url}/session/stop",
                    json={"accountId": self._account_id},
                )
            self._connected = False
        except Exception as e:
            logger.warning(f"[baileys] Error stopping: {e}")

    async def logout(self) -> None:
        """Logout and destroy Baileys session."""
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                await client.post(
                    f"{self._service_url}/session/logout",
                    json={"accountId": self._account_id},
                )
            self._connected = False
            self._phone = None
        except Exception as e:
            logger.warning(f"[baileys] Error logging out: {e}")

    # ── Status ───────────────────────────────────────────

    async def get_connection_state(self) -> ConnectionState:
        if not self._connected:
            return ConnectionState.DISCONNECTED
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(
                    f"{self._service_url}/session/status/{self._account_id}",
                )
                if resp.status_code == 200:
                    data = resp.json()
                    state = data.get("state", "disconnected")
                    mapping = {
                        "connected": ConnectionState.CONNECTED,
                        "connecting": ConnectionState.CONNECTING,
                        "qr_pending": ConnectionState.QR_PENDING,
                        "disconnected": ConnectionState.DISCONNECTED,
                    }
                    return mapping.get(state, ConnectionState.DISCONNECTED)
        except Exception:
            logger.debug("wa.baileys.connection_state_failed", exc_info=True)
        return ConnectionState.DISCONNECTED

    async def get_connection_info(self) -> ConnectionInfo:
        return ConnectionInfo(
            connected=self._connected,
            authenticated=self._connected,
            ready=self._connected,
            phone=self._phone,
            last_event_at=self._last_connected_at,
            last_send_at=self._last_send_at,
            last_error=self._last_error,
            provider_type=self.provider_type,
        )

    def is_connected(self) -> bool:
        return self._connected

    # ── QR Code ──────────────────────────────────────────

    async def get_qr_code(self) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(
                    f"{self._service_url}/session/qr/{self._account_id}",
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("qr")
        except Exception:
            logger.debug("wa.baileys.qr_fetch_failed", exc_info=True)
        return None

    # ── Messaging ────────────────────────────────────────

    async def send_text(self, options: SendOptions) -> SendResult:
        if not self._connected:
            return SendResult(
                success=False,
                error="Baileys not connected",
                error_code="NOT_CONNECTED",
                provider=self.provider_type,
            )

        try:
            async with httpx.AsyncClient(timeout=SEND_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._service_url}/message/send",
                    json={
                        "accountId": self._account_id,
                        "recipient": options.recipient,
                        "text": options.text,
                    },
                )

                self._last_send_at = datetime.utcnow()

                if resp.status_code == 200:
                    data = resp.json()
                    return SendResult(
                        success=data.get("success", False),
                        message_id=data.get("messageId"),
                        error=data.get("error"),
                        provider=self.provider_type,
                    )
                else:
                    return SendResult(
                        success=False,
                        error=f"HTTP {resp.status_code}",
                        provider=self.provider_type,
                    )
        except Exception as e:
            self._last_error = str(e)
            return SendResult(success=False, error=str(e), provider=self.provider_type)

    async def send_media(self, options: SendOptions) -> SendResult:
        # Baileys supports media — implement when service is built
        return SendResult(
            success=False,
            error="Baileys media send not yet implemented",
            error_code="NOT_IMPLEMENTED",
            provider=self.provider_type,
        )

    async def send_typing(self, recipient: str) -> bool:
        return False

    async def mark_as_read(self, message_id: str) -> bool:
        return False

    # ── Contacts ─────────────────────────────────────────

    async def get_contacts(self) -> List[WhatsAppContact]:
        return []

    async def get_contact(self, jid: str) -> Optional[WhatsAppContact]:
        return None

    # ── Session ──────────────────────────────────────────

    async def get_session_info(self) -> Dict[str, Any]:
        return {
            "account_id": self._account_id,
            "provider": "baileys",
            "phone": self._phone,
            "connected": self._connected,
            "experimental": True,
            "last_connected_at": self._last_connected_at.isoformat() if self._last_connected_at else None,
        }

    # ── Health ───────────────────────────────────────────

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._service_url}/health")
                return resp.status_code == 200
        except Exception:
            return False
