"""
WhatsApp Business Cloud API Adapter — Meta oficial.

Adapter para a WhatsApp Business Cloud API (graph.facebook.com).
Canal oficial da Meta: zero risco de ban para campanhas e notificações,
desde que templates aprovados e políticas de business sejam respeitados.

Architecture:
FastAPI → CloudApiAdapter → HTTPS (httpx async) → graph.facebook.com/v{version}/{phone_number_id}/messages

Env vars:
- WHATSAPP_CLOUD_API_TOKEN:             access token permanente (System User)
- WHATSAPP_CLOUD_API_PHONE_NUMBER_ID:   phone number ID do número remetente
- WHATSAPP_CLOUD_API_WABA_ID:           WABA ID (para listar templates)
- WHATSAPP_CLOUD_API_VERSION:           versão da Graph API (default v21.0)
- WHATSAPP_CLOUD_API_TEMPLATE_*:        nomes de templates por evento (ver template_name_for_event)

Notas de implementação:
- Todo o I/O é async (httpx.AsyncClient) — nunca bloqueia o event loop do FastAPI.
- Erros 401/403 viram WhatsAppAuthError; 429 vira WhatsAppRateLimitError com
  `retry_after` (fila e retry ficam a cargo do chamador — sem fallback para
  canais não-oficiais).
- `transport` pode ser injetado (httpx.MockTransport) para testes sem rede.

Diferenças vs. canal não-oficial (Baileys; histórico: whatsapp-web.js):
- Envio exige template aprovado fora da janela de 24h do usuário (erro 131047).
- Dentro da janela de 24h (usuário mandou mensagem), texto livre é permitido.
- Delivery/read receipts chegam via webhook (ver verify_webhook_signature).
"""

import hashlib
import hmac
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

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
    WhatsAppAuthError,
    WhatsAppConnectionError,
    WhatsAppRateLimitError,
)

logger = logging.getLogger("gasflow.whatsapp.cloud_api")

GRAPH_BASE = "https://graph.facebook.com"
DEFAULT_VERSION = "v21.0"
DEFAULT_TIMEOUT = 10
SEND_TIMEOUT = 30

# Cooldown padrão para 429: a Cloud API retorna `retry_after` em segundos no body.
DEFAULT_RETRY_AFTER_S = 60

# Códigos de erro da Meta que merecem dica acionável no erro retornado.
ERR_NOT_IN_24H_WINDOW = 131047


class CloudApiAdapter(WhatsAppProvider):
    """Adapter for the official WhatsApp Business Cloud API."""

    def __init__(
        self,
        account_id: str,
        access_token: str = "",
        phone_number_id: str = "",
        api_version: str = DEFAULT_VERSION,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self._account_id = account_id
        self._access_token = access_token or os.getenv("WHATSAPP_CLOUD_API_TOKEN", "")
        self._phone_number_id = phone_number_id or os.getenv("WHATSAPP_CLOUD_API_PHONE_NUMBER_ID", "")
        self._api_version = api_version or os.getenv("WHATSAPP_CLOUD_API_VERSION", DEFAULT_VERSION)
        self._connected = False
        self._phone: Optional[str] = None
        self._last_error: Optional[str] = None
        self._last_send_at: Optional[datetime] = None
        # Cliente persistente (reuso de conexão) — criado no start() ou
        # imediatamente quando um transport é injetado (testes).
        self._client: Optional[httpx.AsyncClient] = (
            httpx.AsyncClient(transport=transport, timeout=SEND_TIMEOUT) if transport else None
        )

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.META

    @property
    def account_id(self) -> str:
        return self._account_id

    # ── Internals ────────────────────────────────────────

    def _base_url(self) -> str:
        return f"{GRAPH_BASE}/{self._api_version}/{self._phone_number_id}"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    def _configured(self) -> bool:
        return bool(self._access_token and self._phone_number_id)

    @staticmethod
    def _normalize_recipient(recipient: str) -> str:
        """Cloud API espera E.164 sem '+' — ex.: 559181689969."""
        recipient = recipient.strip()
        if "@" in recipient:
            recipient = recipient.split("@")[0]
        if recipient.startswith("+"):
            recipient = recipient[1:]
        return recipient

    async def _request(
        self,
        method: str,
        url: str,
        *,
        timeout: int,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """Executa uma chamada à Graph API via cliente persistente ou efêmero."""
        if self._client is not None:
            return await self._client.request(
                method,
                url,
                headers=self._headers(),
                json=json,
                params=params,
            )
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.request(
                method,
                url,
                headers=self._headers(),
                json=json,
                params=params,
            )

    def _raise_for_auth_and_rate(self, resp: httpx.Response) -> None:
        """Normaliza 401/403 → WhatsAppAuthError e 429 → WhatsAppRateLimitError."""
        if resp.status_code == 429:
            retry_after = DEFAULT_RETRY_AFTER_S
            try:
                retry_after = int(resp.json().get("error", {}).get("retry_after", DEFAULT_RETRY_AFTER_S))
            except Exception:  # noqa: BLE001 — body pode não ser JSON
                pass
            raise WhatsAppRateLimitError(
                f"Cloud API rate limited: HTTP 429 (retry after {retry_after}s)",
                provider="cloud_api",
                retry_after=retry_after,
            )
        if resp.status_code in (401, 403):
            detail = _error_detail(resp)[0]
            self._last_error = detail
            raise WhatsAppAuthError(detail, provider="cloud_api")

    async def _send_payload(self, payload: Dict[str, Any], timeout: int) -> SendResult:
        if not self._configured():
            return SendResult(
                success=False,
                error="Cloud API não configurada: defina WHATSAPP_CLOUD_API_TOKEN e "
                "WHATSAPP_CLOUD_API_PHONE_NUMBER_ID.",
                error_code="NOT_CONFIGURED",
                provider=self.provider_type,
            )
        try:
            resp = await self._request("POST", f"{self._base_url()}/messages", timeout=timeout, json=payload)
        except httpx.TimeoutException:
            self._last_error = "Timeout"
            return SendResult(
                success=False,
                error="Timeout sending message",
                error_code="TIMEOUT",
                provider=self.provider_type,
            )
        except Exception as e:  # noqa: BLE001 — normalizado para SendResult
            self._last_error = str(e)
            return SendResult(
                success=False,
                error=str(e),
                provider=self.provider_type,
            )

        self._last_send_at = datetime.utcnow()
        self._raise_for_auth_and_rate(resp)

        if resp.status_code not in (200, 201):
            message, code = _error_detail(resp)
            self._last_error = message
            if code == ERR_NOT_IN_24H_WINDOW and payload.get("type") == "text":
                message += (
                    " [dica] Fora da janela de 24h: use send_template com um "
                    "template aprovado para este destinatário."
                )
            logger.warning(f"[cloud_api] send failed: HTTP {resp.status_code}: {message}")
            return SendResult(
                success=False,
                error=message,
                error_code=f"HTTP_{resp.status_code}",
                provider=self.provider_type,
            )

        data = resp.json()
        return SendResult(
            success=True,
            message_id=_extract_message_id(data),
            provider=self.provider_type,
        )

    # ── Lifecycle ────────────────────────────────────────

    async def start(self) -> None:
        """Valida credenciais consultando o número registrado e abre cliente persistente."""
        if not self._configured():
            self._connected = False
            raise WhatsAppConnectionError(
                "Cloud API não configurada: WHATSAPP_CLOUD_API_TOKEN e "
                "WHATSAPP_CLOUD_API_PHONE_NUMBER_ID são obrigatórios.",
                provider="cloud_api",
            )
        try:
            resp = await self._request(
                "GET",
                self._base_url(),
                timeout=DEFAULT_TIMEOUT,
                params={"fields": "verified_name,display_phone_number,quality_rating"},
            )
        except (WhatsAppAuthError, WhatsAppConnectionError):
            raise
        except Exception as e:  # noqa: BLE001
            self._connected = False
            self._last_error = str(e)
            raise WhatsAppConnectionError(
                f"Cloud API connection failed: {e}",
                provider="cloud_api",
            )

        self._raise_for_auth_and_rate(resp)

        if resp.status_code != 200:
            self._connected = False
            self._last_error = _error_detail(resp)[0]
            raise WhatsAppConnectionError(
                f"Cloud API probe failed: HTTP {resp.status_code}",
                provider="cloud_api",
            )

        data = resp.json()
        self._phone = data.get("display_phone_number")
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=SEND_TIMEOUT)
        self._connected = True
        logger.info(f"[cloud_api] connected phone={self._phone} " f"quality={data.get('quality_rating', 'unknown')}")

    async def stop(self) -> None:
        """Fecha o cliente HTTP; a Cloud API é stateless do lado do backend."""
        self._connected = False
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    async def logout(self) -> None:
        self._connected = False
        self._phone = None

    # ── Status ───────────────────────────────────────────

    async def get_connection_state(self) -> ConnectionState:
        return ConnectionState.CONNECTED if self._connected else ConnectionState.DISCONNECTED

    async def get_connection_info(self) -> ConnectionInfo:
        return ConnectionInfo(
            connected=self._connected,
            authenticated=self._configured() and self._connected,
            ready=self._connected,
            phone=self._phone,
            last_send_at=self._last_send_at,
            last_error=self._last_error,
            provider_type=self.provider_type,
        )

    def is_connected(self) -> bool:
        return self._connected

    # ── QR Code ──────────────────────────────────────────

    async def get_qr_code(self) -> Optional[str]:
        """Cloud API não usa QR code — pairing é feito no Meta Business Manager."""
        return None

    # ── Messaging ────────────────────────────────────────

    async def send_text(self, options: SendOptions) -> SendResult:
        """Texto livre — permitido apenas dentro da janela de 24h do usuário.

        Fora da janela a API rejeita (131047) e o template deve ser usado.
        """
        return await self._send_payload(
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": self._normalize_recipient(options.recipient),
                "type": "text",
                "text": {"preview_url": True, "body": options.text},
            },
            SEND_TIMEOUT,
        )

    async def send_media(self, options: SendOptions) -> SendResult:
        """Envia mídia por link público (image/audio/document/video/sticker)."""
        media = options.media
        if not media or not media.url:
            return SendResult(
                success=False,
                error="Cloud API send_media requer WhatsAppMedia.url (link público).",
                error_code="MEDIA_URL_REQUIRED",
                provider=self.provider_type,
            )
        media_type = options.media_type.value
        if media_type not in ("image", "audio", "video", "document", "sticker"):
            return SendResult(
                success=False,
                error=f"Tipo de mídia não suportado: {media_type}",
                error_code="MEDIA_TYPE_UNSUPPORTED",
                provider=self.provider_type,
            )
        media_payload: Dict[str, Any] = {"link": media.url}
        if media.filename and media_type == "document":
            media_payload["filename"] = media.filename
        if options.text and media_type in ("image", "video", "document"):
            media_payload["caption"] = options.text
        return await self._send_payload(
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": self._normalize_recipient(options.recipient),
                "type": media_type,
                media_type: media_payload,
            },
            SEND_TIMEOUT,
        )

    async def send_template(
        self,
        recipient: str,
        template_name: str,
        language_code: str = "pt_BR",
        body_params: Optional[List[str]] = None,
    ) -> SendResult:
        """Envia template aprovado — o mecanismo para campanhas/notificações.

        Nomes de template por evento podem ser resolvidos via env com
        `template_name_for_event("DELIVERY_CONFIRMED")`, etc.
        """
        template: Dict[str, Any] = {
            "name": template_name,
            "language": {"code": language_code},
        }
        if body_params:
            template["components"] = [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in body_params],
                }
            ]
        return await self._send_payload(
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": self._normalize_recipient(recipient),
                "type": "template",
                "template": template,
            },
            SEND_TIMEOUT,
        )

    async def list_message_templates(
        self,
        waba_id: str = "",
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lista templates do WABA (nome, status, idioma, categoria).

        Requer WHATSAPP_CLOUD_API_WABA_ID (ou o parâmetro `waba_id`).
        Usado para validar que os templates configurados por evento estão APPROVED.
        """
        waba = waba_id or os.getenv("WHATSAPP_CLOUD_API_WABA_ID", "")
        if not waba:
            raise WhatsAppConnectionError(
                "WABA ID não configurado: defina WHATSAPP_CLOUD_API_WABA_ID " "ou passe waba_id explicitamente.",
                provider="cloud_api",
            )
        params: Dict[str, Any] = {
            "fields": "name,status,language,category",
            "limit": 200,
        }
        if status:
            params["status"] = status
        resp = await self._request(
            "GET",
            f"{GRAPH_BASE}/{self._api_version}/{waba}/message_templates",
            timeout=DEFAULT_TIMEOUT,
            params=params,
        )
        self._raise_for_auth_and_rate(resp)
        if resp.status_code != 200:
            raise WhatsAppConnectionError(
                f"list_message_templates failed: HTTP {resp.status_code}",
                provider="cloud_api",
            )
        return list(resp.json().get("data", []))

    async def send_typing(self, recipient: str) -> bool:
        """Cloud API não expõe typing indicator — no-op."""
        return False

    async def mark_as_read(self, message_id: str) -> bool:
        if not self._configured():
            return False
        try:
            resp = await self._request(
                "POST",
                f"{self._base_url()}/messages",
                timeout=DEFAULT_TIMEOUT,
                json={"messaging_product": "whatsapp", "status": "read", "message_id": message_id},
            )
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    # ── Contacts ─────────────────────────────────────────

    async def get_contacts(self) -> List[WhatsAppContact]:
        """Cloud API não expõe a lista de contatos do telefone —
        contatos são gerenciados no GasFlow."""
        return []

    async def get_contact(self, jid: str) -> Optional[WhatsAppContact]:
        phone = self._normalize_recipient(jid)
        return WhatsAppContact(jid=jid, phone=phone) if phone else None

    # ── Session ──────────────────────────────────────────

    async def get_session_info(self) -> Dict[str, Any]:
        return {
            "provider": "cloud_api",
            "phone_number_id": self._phone_number_id,
            "phone": self._phone,
            "api_version": self._api_version,
            "waba_id_configured": bool(os.getenv("WHATSAPP_CLOUD_API_WABA_ID", "")),
            "configured": self._configured(),
            "connected": self._connected,
        }

    # ── Webhook helpers (entrega/leitura) ────────────────

    @staticmethod
    def verify_webhook_signature(app_secret: str, payload_body: bytes, header: str) -> bool:
        """Valida X-Hub-Signature-256 do webhook da Meta.

        Uso no endpoint de webhook:
            sig = request.headers.get("X-Hub-Signature-256", "")
            assert CloudApiAdapter.verify_webhook_signature(
                WHATSAPP_APP_SECRET, await request.body(), sig
            )
        """
        if not app_secret or not header.startswith("sha256="):
            return False
        expected = hmac.new(app_secret.encode("utf-8"), payload_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", header)

    @staticmethod
    def parse_status_event(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extrai eventos de status (sent/delivered/read/failed) do webhook body.

        Retorna lista de dicts: {message_id, status, recipient, timestamp, errors}.
        """
        events: List[Dict[str, Any]] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for status in value.get("statuses", []):
                    events.append(
                        {
                            "message_id": status.get("id"),
                            "status": status.get("status"),
                            "recipient": status.get("recipient_id"),
                            "timestamp": status.get("timestamp"),
                            "errors": status.get("errors"),
                        }
                    )
        return events

    @staticmethod
    def parse_incoming_message(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extrai mensagens recebidas do webhook body.

        Retorna lista de dicts: {message_id, from, text, timestamp, type}.
        """
        messages: List[Dict[str, Any]] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    messages.append(
                        {
                            "message_id": msg.get("id"),
                            "from": msg.get("from"),
                            "type": msg.get("type"),
                            "text": (msg.get("text") or {}).get("body", ""),
                            "timestamp": msg.get("timestamp"),
                        }
                    )
        return messages


def template_name_for_event(event: str) -> str:
    """Resolve o nome de template por evento a partir de env.

    Ex.: template_name_for_event("ORDER_RECEIVED") →
         env WHATSAPP_CLOUD_API_TEMPLATE_ORDER_RECEIVED
    """
    return os.getenv(f"WHATSAPP_CLOUD_API_TEMPLATE_{event.upper()}", "")


# ── Helpers ──────────────────────────────────────────────


def _error_detail(resp: httpx.Response) -> tuple:
    """Extrai (message, code) do corpo de erro da Graph API."""
    try:
        err = resp.json().get("error", {})
        return err.get("message", f"HTTP {resp.status_code}"), err.get("code")
    except Exception:  # noqa: BLE001
        return f"HTTP {resp.status_code}", None


def _extract_message_id(data: Dict[str, Any]) -> Optional[str]:
    messages = data.get("messages") or []
    return messages[0].get("id") if messages else None
