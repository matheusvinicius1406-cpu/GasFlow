"""
WhatsApp Cloud API Adapter — unit tests (sem chamadas reais à Meta).

Usa httpx.MockTransport injetado no adapter — sem patching global e sem rede.
Cobre: configuração, normalização E.164, erros normalizados (401/429/4xx),
dica da janela de 24h (131047), mídia por link, templates, listagem de
templates do WABA, webhook signature, parsing de eventos e factory.
"""

import asyncio
import hashlib
import hmac
import json

import httpx
import pytest

from app.domain.whatsapp_provider.models import (
    SendOptions,
    WhatsAppMedia,
    MediaType,
    ProviderType,
)
from app.domain.whatsapp_provider.errors import (
    WhatsAppAuthError,
    WhatsAppConnectionError,
    WhatsAppRateLimitError,
)
from app.infrastructure.whatsapp_provider.cloud_api_adapter import (
    CloudApiAdapter,
    template_name_for_event,
)
from app.infrastructure.whatsapp_provider.factory import create_provider


# ── Fixtures / helpers ───────────────────────────────────


def _json_response(status_code: int, body: dict) -> httpx.Response:
    return httpx.Response(status_code=status_code, json=body)


def _send_ok() -> httpx.Response:
    return _json_response(200, {"messages": [{"id": "wamid.TEST123"}]})


def _adapter_with(handler) -> CloudApiAdapter:
    """Adapter configurado com transport mock — nenhuma chamada real."""
    return CloudApiAdapter(
        account_id="primary",
        access_token="test-token",
        phone_number_id="123456789",
        api_version="v21.0",
        transport=httpx.MockTransport(handler),
    )


def _capturing_handler(captured: dict, response: httpx.Response):
    """Handler que captura o payload POST e devolve a resposta fixa."""

    def h(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured["url"] = str(request.url)
            captured["json"] = json.loads(request.content.decode())
            captured["auth"] = request.headers.get("Authorization", "")
        return response

    return h


@pytest.fixture
def adapter() -> CloudApiAdapter:
    return _adapter_with(lambda request: _send_ok())


# ── Configuração / Lifecycle ─────────────────────────────


class TestConfig:
    def test_provider_type_is_meta(self, adapter: CloudApiAdapter):
        assert adapter.provider_type == ProviderType.META

    def test_unconfigured_adapter_rejects_send(self):
        a = CloudApiAdapter(account_id="primary")
        result = asyncio.run(a.send_text(SendOptions(recipient="5591999999999", text="oi")))
        assert result.success is False
        assert result.error_code == "NOT_CONFIGURED"

    def test_start_requires_configuration(self):
        a = CloudApiAdapter(account_id="primary")
        with pytest.raises(WhatsAppConnectionError):
            asyncio.run(a.start())

    @pytest.mark.asyncio
    async def test_start_success_opens_persistent_client(self):
        def h(request: httpx.Request) -> httpx.Response:
            return _json_response(
                200,
                {"verified_name": "Marcos Gas", "display_phone_number": "559199999-9999", "quality_rating": "GREEN"},
            )

        a = _adapter_with(h)
        await a.start()
        assert a.is_connected() is True
        assert a._client is not None
        info = await a.get_connection_info()
        assert info.connected is True
        assert info.phone == "559199999-9999"
        await a.stop()
        assert a._client is None
        assert a.is_connected() is False

    @pytest.mark.asyncio
    async def test_start_auth_failure_raises(self):
        def h(request: httpx.Request) -> httpx.Response:
            return _json_response(401, {"error": {"message": "Invalid token", "code": 190}})

        a = _adapter_with(h)
        with pytest.raises(WhatsAppAuthError):
            await a.start()
        assert a.is_connected() is False


# ── Normalização ─────────────────────────────────────────


class TestNormalization:
    def test_recipient_plain_number(self, adapter: CloudApiAdapter):
        assert adapter._normalize_recipient("5591999999999") == "5591999999999"

    def test_recipient_strips_plus(self, adapter: CloudApiAdapter):
        assert adapter._normalize_recipient("+5591999999999") == "5591999999999"

    def test_recipient_strips_jid_suffix(self, adapter: CloudApiAdapter):
        assert adapter._normalize_recipient("5591999999999@c.us") == "5591999999999"


# ── Envio ────────────────────────────────────────────────


class TestSend:
    @pytest.mark.asyncio
    async def test_send_text_payload_and_auth_header(self):
        captured: dict = {}
        a = _adapter_with(_capturing_handler(captured, _send_ok()))
        result = await a.send_text(SendOptions(recipient="+5591999999999", text="Seu gás chegou!"))
        assert result.success is True
        assert result.message_id == "wamid.TEST123"
        assert result.provider == ProviderType.META
        assert captured["auth"] == "Bearer test-token"
        assert captured["json"]["to"] == "5591999999999"  # '+' removido
        assert captured["json"]["type"] == "text"
        assert captured["json"]["text"]["body"] == "Seu gás chegou!"

    @pytest.mark.asyncio
    async def test_send_text_http_error_400(self):
        a = _adapter_with(lambda request: _json_response(400, {"error": {"message": "Invalid parameter", "code": 100}}))
        result = await a.send_text(SendOptions(recipient="5591999999999", text="oi"))
        assert result.success is False
        assert "Invalid parameter" in (result.error or "")
        assert result.error_code == "HTTP_400"

    @pytest.mark.asyncio
    async def test_send_text_outside_24h_window_gets_hint(self):
        a = _adapter_with(
            lambda request: _json_response(
                400,
                {
                    "error": {
                        "message": "Re-engagement message",
                        "code": 131047,
                        "error_data": {"details": "Message undeliverable"},
                    }
                },
            )
        )
        result = await a.send_text(SendOptions(recipient="5591999999999", text="oi"))
        assert result.success is False
        assert "send_template" in (result.error or "")

    @pytest.mark.asyncio
    async def test_send_text_auth_error_raises(self):
        a = _adapter_with(lambda request: _json_response(401, {"error": {"message": "Invalid token"}}))
        with pytest.raises(WhatsAppAuthError):
            await a.send_text(SendOptions(recipient="5591999999999", text="oi"))

    @pytest.mark.asyncio
    async def test_send_text_rate_limit_raises_with_retry_after(self):
        a = _adapter_with(
            lambda request: _json_response(429, {"error": {"message": "rate limited", "retry_after": 30}})
        )
        with pytest.raises(WhatsAppRateLimitError) as exc_info:
            await a.send_text(SendOptions(recipient="5591999999999", text="oi"))
        assert exc_info.value.retry_after == 30

    @pytest.mark.asyncio
    async def test_send_media_requires_url(self, adapter: CloudApiAdapter):
        result = await adapter.send_media(SendOptions(recipient="5591999999999", media=None))
        assert result.success is False
        assert result.error_code == "MEDIA_URL_REQUIRED"

    @pytest.mark.asyncio
    async def test_send_media_document_with_link(self):
        captured: dict = {}
        a = _adapter_with(_capturing_handler(captured, _send_ok()))
        result = await a.send_media(
            SendOptions(
                recipient="5591999999999",
                text="Olha a nota",
                media=WhatsAppMedia(url="https://cdn.gasflow.app/nota.pdf", filename="nota.pdf"),
                media_type=MediaType.DOCUMENT,
            )
        )
        assert result.success is True
        assert captured["json"]["type"] == "document"
        assert captured["json"]["document"]["link"] == "https://cdn.gasflow.app/nota.pdf"
        assert captured["json"]["document"]["filename"] == "nota.pdf"
        assert captured["json"]["document"]["caption"] == "Olha a nota"

    @pytest.mark.asyncio
    async def test_send_media_unsupported_type(self, adapter: CloudApiAdapter):
        result = await adapter.send_media(
            SendOptions(
                recipient="5591999999999",
                media=WhatsAppMedia(url="https://x/y"),
                media_type=MediaType.LOCATION,
            )
        )
        assert result.success is False
        assert result.error_code == "MEDIA_TYPE_UNSUPPORTED"

    @pytest.mark.asyncio
    async def test_send_template_with_params(self):
        captured: dict = {}
        a = _adapter_with(_capturing_handler(captured, _send_ok()))
        result = await a.send_template(
            "5591999999999",
            "entrega_confirmada",
            language_code="pt_BR",
            body_params=["João", "R$ 120,00"],
        )
        assert result.success is True
        template = captured["json"]["template"]
        assert template["name"] == "entrega_confirmada"
        assert template["language"]["code"] == "pt_BR"
        assert template["components"][0]["parameters"] == [
            {"type": "text", "text": "João"},
            {"type": "text", "text": "R$ 120,00"},
        ]


# ── Listagem de templates (WABA) ─────────────────────────


class TestListTemplates:
    @pytest.mark.asyncio
    async def test_list_templates_success(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_CLOUD_API_WABA_ID", "WABA123")
        templates = {
            "data": [
                {"name": "entrega_confirmada", "status": "APPROVED", "language": "pt_BR", "category": "UTILITY"},
                {"name": "rascunho", "status": "PENDING", "language": "pt_BR", "category": "MARKETING"},
            ]
        }
        captured: dict = {}

        def h(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return _json_response(200, templates)

        a = _adapter_with(h)
        data = await a.list_message_templates()
        assert "WABA123/message_templates" in captured["url"]
        assert len(data) == 2
        approved = [t for t in data if t["status"] == "APPROVED"]
        assert approved[0]["name"] == "entrega_confirmada"

    @pytest.mark.asyncio
    async def test_list_templates_without_waba_raises(self, monkeypatch):
        monkeypatch.delenv("WHATSAPP_CLOUD_API_WABA_ID", raising=False)
        a = _adapter_with(lambda request: _send_ok())
        with pytest.raises(WhatsAppConnectionError):
            await a.list_message_templates()


# ── Webhook ──────────────────────────────────────────────


class TestWebhook:
    def test_signature_valid(self):
        secret = "my-app-secret"
        body = json.dumps({"entry": []}).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert CloudApiAdapter.verify_webhook_signature(secret, body, sig) is True

    def test_signature_invalid(self):
        body = b'{"entry": []}'
        bad = "sha256=" + "0" * 64
        assert CloudApiAdapter.verify_webhook_signature("secret", body, bad) is False

    def test_signature_missing_prefix(self):
        assert CloudApiAdapter.verify_webhook_signature("secret", b"{}", "d41d8cd9") is False

    def test_parse_status_event(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": "wamid.X",
                                        "status": "delivered",
                                        "recipient_id": "5591999999999",
                                        "timestamp": "1700000000",
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        events = CloudApiAdapter.parse_status_event(payload)
        assert len(events) == 1
        assert events[0]["status"] == "delivered"
        assert events[0]["message_id"] == "wamid.X"

    def test_parse_incoming_message(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "id": "wamid.IN",
                                        "from": "5591999999999",
                                        "type": "text",
                                        "text": {"body": "Oi, pedido 42 chegou?"},
                                        "timestamp": "1700000000",
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        msgs = CloudApiAdapter.parse_incoming_message(payload)
        assert len(msgs) == 1
        assert msgs[0]["text"] == "Oi, pedido 42 chegou?"


# ── Templates por evento ─────────────────────────────────


class TestTemplateNames:
    def test_env_resolution(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_CLOUD_API_TEMPLATE_ORDER_RECEIVED", "pedido_recebido")
        assert template_name_for_event("ORDER_RECEIVED") == "pedido_recebido"

    def test_missing_env_returns_empty(self, monkeypatch):
        monkeypatch.delenv("WHATSAPP_CLOUD_API_TEMPLATE_MISSING", raising=False)
        assert template_name_for_event("MISSING") == ""


# ── Factory ──────────────────────────────────────────────


class TestFactory:
    def test_factory_creates_cloud_api(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_PROVIDER", "cloud_api")
        provider = create_provider("primary", "cloud_api")
        assert isinstance(provider, CloudApiAdapter)

    def test_factory_accepts_meta_alias(self, monkeypatch):
        provider = create_provider("primary", "meta")
        assert isinstance(provider, CloudApiAdapter)

    def test_session_info_shape(self):
        a = CloudApiAdapter(account_id="primary", access_token="t", phone_number_id="123")
        info = asyncio.run(a.get_session_info())
        assert info["provider"] == "cloud_api"
        assert info["configured"] is True
        assert info["phone_number_id"] == "123"
        assert "waba_id_configured" in info
