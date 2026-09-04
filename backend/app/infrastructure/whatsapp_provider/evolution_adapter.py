"""
Evolution API Provider Adapter — WAVE 2

Adapter for Evolution API (https://github.com/EvolutionAPI/evolution-api).
Apache 2.0 licensed.

Architecture:
FastAPI → EvolutionAdapter → HTTP → Evolution API → WhatsApp
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

logger = logging.getLogger("gasflow.whatsapp.evolution")

DEFAULT_TIMEOUT = 10
SEND_TIMEOUT = 30


class EvolutionAdapter(WhatsAppProvider):
    """Adapter for Evolution API.

    Requires:
    - Evolution API running (Docker or standalone)
    - Instance created via Evolution API
    - API key configured
    """

    def __init__(
        self,
        account_id: str,
        service_url: str = "http://localhost:8080",
        api_key: str = "",
        instance_name: str = "gasflow",
    ):
        self._account_id = account_id
        self._service_url = service_url.rstrip("/")
        self._api_key = api_key
        self._instance_name = instance_name
        self._connected = False
        self._phone: Optional[str] = None
        self._last_connected_at: Optional[datetime] = None
        self._last_send_at: Optional[datetime] = None
        self._last_error: Optional[str] = None

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.EVOLUTION

    @property
    def account_id(self) -> str:
        return self._account_id

    def _headers(self) -> Dict[str, str]:
        """Build request headers with API key."""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["apikey"] = self._api_key
        return headers

    # ── Lifecycle ────────────────────────────────────────

    async def start(self) -> None:
        """Connect to Evolution API instance."""
        try:
            # Check if instance exists, create if not
            instance = await self._get_instance()
            if not instance:
                await self._create_instance()

            # Connect the instance
            await self._connect_instance()
            self._connected = True
            self._last_connected_at = datetime.utcnow()
            logger.info(f"[evolution] Connected instance {self._instance_name}")
        except Exception as e:
            self._connected = False
            self._last_error = str(e)
            raise WhatsAppConnectionError(
                f"Evolution API connection failed: {e}",
                provider="evolution",
            )

    async def stop(self) -> None:
        """Disconnect from Evolution API."""
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                await client.post(
                    f"{self._service_url}/instance/disconnect/{self._instance_name}",
                    headers=self._headers(),
                )
            self._connected = False
        except Exception as e:
            logger.warning(f"[evolution] Error stopping: {e}")

    async def logout(self) -> None:
        """Logout and delete instance."""
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                await client.delete(
                    f"{self._service_url}/instance/delete/{self._instance_name}",
                    headers=self._headers(),
                )
            self._connected = False
            self._phone = None
        except Exception as e:
            logger.warning(f"[evolution] Error logging out: {e}")

    # ── Status ───────────────────────────────────────────

    async def get_connection_state(self) -> ConnectionState:
        try:
            instance = await self._get_instance()
            if not instance:
                return ConnectionState.DISCONNECTED
            state = instance.get("state", "disconnected")
            mapping = {
                "open": ConnectionState.CONNECTED,
                "connecting": ConnectionState.CONNECTING,
                "qr_pending": ConnectionState.QR_PENDING,
                "disconnected": ConnectionState.DISCONNECTED,
            }
            return mapping.get(state, ConnectionState.DISCONNECTED)
        except Exception:
            return ConnectionState.DISCONNECTED

    async def get_connection_info(self) -> ConnectionInfo:
        try:
            instance = await self._get_instance()
            connected = instance.get("state") == "open" if instance else False
            return ConnectionInfo(
                connected=connected,
                authenticated=connected,
                ready=connected,
                phone=self._phone,
                last_event_at=self._last_connected_at,
                last_send_at=self._last_send_at,
                last_error=self._last_error,
                provider_type=self.provider_type,
            )
        except Exception as e:
            return ConnectionInfo(last_error=str(e), provider_type=self.provider_type)

    def is_connected(self) -> bool:
        return self._connected

    # ── QR Code ──────────────────────────────────────────

    async def get_qr_code(self) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(
                    f"{self._service_url}/instance/connect/{self._instance_name}",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("base64")
        except Exception:
            pass
        return None

    # ── Messaging ────────────────────────────────────────

    async def send_text(self, options: SendOptions) -> SendResult:
        if not self._connected:
            return SendResult(
                success=False,
                error="Evolution API not connected",
                error_code="NOT_CONNECTED",
                provider=self.provider_type,
            )

        try:
            async with httpx.AsyncClient(timeout=SEND_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._service_url}/message/sendText/{self._instance_name}",
                    headers=self._headers(),
                    json={
                        "number": options.recipient,
                        "text": options.text,
                    },
                )

                self._last_send_at = datetime.utcnow()

                if resp.status_code == 200 or resp.status_code == 201:
                    data = resp.json()
                    key = data.get("key", {})
                    return SendResult(
                        success=True,
                        message_id=key.get("id"),
                        provider=self.provider_type,
                    )
                else:
                    return SendResult(
                        success=False,
                        error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                        provider=self.provider_type,
                    )
        except Exception as e:
            self._last_error = str(e)
            return SendResult(success=False, error=str(e), provider=self.provider_type)

    async def send_media(self, options: SendOptions) -> SendResult:
        # Evolution API supports media via sendMedia endpoint
        if not options.media or not options.media.url:
            return SendResult(success=False, error="No media URL provided", provider=self.provider_type)

        try:
            async with httpx.AsyncClient(timeout=SEND_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._service_url}/message/sendMedia/{self._instance_name}",
                    headers=self._headers(),
                    json={
                        "number": options.recipient,
                        "mediatype": options.media_type.value,
                        "media": options.media.url,
                        "caption": options.text,
                    },
                )

                self._last_send_at = datetime.utcnow()

                if resp.status_code in (200, 201):
                    data = resp.json()
                    key = data.get("key", {})
                    return SendResult(
                        success=True,
                        message_id=key.get("id"),
                        provider=self.provider_type,
                    )
                else:
                    return SendResult(
                        success=False,
                        error=f"HTTP {resp.status_code}",
                        provider=self.provider_type,
                    )
        except Exception as e:
            return SendResult(success=False, error=str(e), provider=self.provider_type)

    async def send_typing(self, recipient: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                await client.post(
                    f"{self._service_url}/chat/presence/{self._instance_name}",
                    headers=self._headers(),
                    json={"number": recipient, "presence": "composing"},
                )
                return True
        except Exception:
            return False

    async def mark_as_read(self, message_id: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                await client.post(
                    f"{self._service_url}/chat/markIsRead/{self._instance_name}",
                    headers=self._headers(),
                    json={"key": {"id": message_id}},
                )
                return True
        except Exception:
            return False

    # ── Contacts ─────────────────────────────────────────

    async def get_contacts(self) -> List[WhatsAppContact]:
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(
                    f"{self._service_url}/chat/findContacts/{self._instance_name}",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    contacts = data if isinstance(data, list) else data.get("contacts", [])
                    return [
                        WhatsAppContact(
                            jid=c.get("jid", ""),
                            phone=c.get("remoteJid", "").replace("@s.whatsapp.net", ""),
                            name=c.get("pushName"),
                            push_name=c.get("pushName"),
                            is_group=c.get("jid", "").endswith("@g.us"),
                        )
                        for c in contacts
                    ]
        except Exception as e:
            logger.warning(f"[evolution] Error getting contacts: {e}")
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
            "provider": "evolution",
            "instance": self._instance_name,
            "phone": self._phone,
            "connected": self._connected,
            "last_connected_at": self._last_connected_at.isoformat() if self._last_connected_at else None,
        }

    # ── Health ───────────────────────────────────────────

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{self._service_url}/instance/fetchInstances",
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False

    # ── Private helpers ──────────────────────────────────

    async def _get_instance(self) -> Optional[Dict[str, Any]]:
        """Get instance info from Evolution API."""
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(
                    f"{self._service_url}/instance/fetchInstances",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    instances = data if isinstance(data, list) else data.get("instances", [])
                    for inst in instances:
                        if inst.get("instanceName") == self._instance_name:
                            return inst
        except Exception:
            pass
        return None

    async def _create_instance(self) -> None:
        """Create a new Evolution API instance."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{self._service_url}/instance/create",
                headers=self._headers(),
                json={
                    "instanceName": self._instance_name,
                    "integration": "WHATSAPP-BAILEYS",
                    "qrcode": True,
                },
            )
            if resp.status_code not in (200, 201):
                raise Exception(f"Failed to create instance: {resp.text}")

    async def _connect_instance(self) -> None:
        """Connect an Evolution API instance."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(
                f"{self._service_url}/instance/connect/{self._instance_name}",
                headers=self._headers(),
            )
            if resp.status_code != 200:
                raise Exception(f"Failed to connect instance: {resp.text}")
