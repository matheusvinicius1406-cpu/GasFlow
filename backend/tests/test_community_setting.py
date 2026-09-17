"""
Community Invite Link Setting Tests — F5

Testa a setting whatsapp.community_invite_link.
"""

import pytest
from app.domain.settings.models import DEFAULT_SETTINGS, SETTING_CATEGORIES


class TestCommunityInviteLinkSetting:
    def test_setting_exists_in_defaults(self):
        """Setting está registrada em DEFAULT_SETTINGS."""
        keys = [s[0] for s in DEFAULT_SETTINGS]
        assert "whatsapp.community_invite_link" in keys

    def test_setting_default_is_empty(self):
        """Valor default é string vazia (desabilitado)."""
        for key, cat, value, desc in DEFAULT_SETTINGS:
            if key == "whatsapp.community_invite_link":
                assert value == ""
                assert cat == "whatsapp"
                return
        pytest.fail("Setting não encontrada")

    def test_setting_description_mentions_disabled(self):
        """Descrição menciona que vazio = desabilitado."""
        for key, cat, value, desc in DEFAULT_SETTINGS:
            if key == "whatsapp.community_invite_link":
                assert "desabilitado" in desc.lower()
                return
        pytest.fail("Setting não encontrada")

    def test_whatsapp_category_exists(self):
        """Categoria 'whatsapp' está na lista de categorias."""
        assert "whatsapp" in SETTING_CATEGORIES
