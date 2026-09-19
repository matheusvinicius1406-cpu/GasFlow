"""
Community Invite Service Tests — F5

Testa: should_send_community_invite, is_already_invited, mark_invited,
queue_community_invite (skip sem bridge, idempotência).
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.application.community.service import (
    should_send_community_invite,
    is_already_invited,
    mark_invited,
    queue_community_invite,
    _invite_sent,
)


@pytest.fixture(autouse=True)
def clean_dedup():
    """Limpa dedup entre testes."""
    _invite_sent.clear()
    yield
    _invite_sent.clear()


class TestCommunityInvite:
    @patch("app.application.community.service._get_setting")
    def test_should_send_when_link_valid(self, mock_setting):
        """Retorna True quando link é válido."""
        mock_setting.return_value = "https://chat.whatsapp.com/abc123"
        assert should_send_community_invite() is True

    @patch("app.application.community.service._get_setting")
    def test_should_not_send_when_link_empty(self, mock_setting):
        """Retorna False quando link é vazio."""
        mock_setting.return_value = ""
        assert should_send_community_invite() is False

    @patch("app.application.community.service._get_setting")
    def test_should_not_send_when_link_invalid(self, mock_setting):
        """Retorna False quando link não começa com https://chat.whatsapp.com/."""
        mock_setting.return_value = "https://example.com/invite"
        assert should_send_community_invite() is False

    def test_is_not_invited_initially(self):
        """Cliente não convidado retorna False."""
        assert is_already_invited("000001") is False

    def test_mark_invited_prevents_resend(self):
        """Marcar como convidado impede reenvio."""
        mark_invited("000001")
        assert is_already_invited("000001") is True

    @patch("app.application.community.service._get_setting")
    def test_queue_skips_when_link_empty(self, mock_setting):
        """Não enfileira quando link está vazio."""
        mock_setting.return_value = ""
        result = queue_community_invite("000001", "João", "11999990000")
        assert result is None

    @patch("app.application.community.service._get_setting")
    def test_queue_idempotent(self, mock_setting):
        """Segunda chamada com mesmo cliente é skipada."""
        mock_setting.return_value = "https://chat.whatsapp.com/abc123"

        # Mock da bridge para evitar envio real
        with patch("app.application.whatsapp_automation.whatsapp_bridge.WhatsAppSendBridge") as mock_bridge:
            # F9.1: bridge expõe send_message (async) — send_text nunca existiu
            mock_bridge.return_value.send_message = AsyncMock(
                return_value={"success": True, "message_id": "m1", "error": None}
            )
            result1 = queue_community_invite("000001", "João", "11999990000")
            assert result1["status"] == "sent"

        # Segunda chamada — já convidado
        result2 = queue_community_invite("000001", "João", "11999990000")
        assert result2 is None

    @patch("app.application.community.service._get_setting")
    def test_queue_calls_send_message(self, mock_setting):
        """F9.1 bugfix: convite chama bridge.send_message com o texto do link."""
        mock_setting.return_value = "https://chat.whatsapp.com/abc123"

        with patch("app.application.whatsapp_automation.whatsapp_bridge.WhatsAppSendBridge") as mock_bridge:
            instance = mock_bridge.return_value
            instance.send_message = AsyncMock(return_value={"success": True, "message_id": "m2", "error": None})
            result = queue_community_invite("000002", "Maria", "(11) 98888-7777")

        assert result["status"] == "sent"
        instance.send_message.assert_called_once()
        args, kwargs = instance.send_message.call_args
        # Telefone normalizado para dígitos
        assert (args[0] if args else kwargs.get("phone_digits")) == "11988887777"
        # Mensagem contém o link do community
        text = args[1] if len(args) > 1 else kwargs.get("message")
        assert "https://chat.whatsapp.com/abc123" in text
