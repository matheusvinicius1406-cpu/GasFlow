"""F4.5 — Store TTL dos limites do WhatsApp (rate limit + cap de ofertas).

Cobre:
- allow(): sliding window em memória (3/hora — mesma regra do signup)
- mark()/is_marked(): marcação única com expiração (cap 1 oferta/conversa)
- Integração gateway: cap 1/conversa persistido no store compartilhado
- Integração tools_impl: rate limit do auto-cadastro via store
- Singleton/reset para isolamento entre testes
"""

import time

import pytest

from app.core.whatsapp_limits import (
    WhatsAppLimitStore,
    get_whatsapp_limit_store,
    reset_whatsapp_limit_store,
)


@pytest.fixture(autouse=True)
def _isolated_store():
    """Singleton limpo por teste (senão contagem vaza entre testes)."""
    reset_whatsapp_limit_store()
    yield
    reset_whatsapp_limit_store()


class TestMemorySlidingWindow:
    def test_allow_within_limit(self):
        store = WhatsAppLimitStore()
        for _ in range(3):
            allowed, _ = store.allow("k", 3, 3600)
            assert allowed is True

    def test_allow_blocks_after_limit(self):
        store = WhatsAppLimitStore()
        for _ in range(3):
            store.allow("k", 3, 3600)
        allowed, count = store.allow("k", 3, 3600)
        assert allowed is False
        assert count >= 3

    def test_window_expiry_frees_key(self):
        store = WhatsAppLimitStore()
        # Janela de 0.05s: enche, espera expirar, libera de novo.
        for _ in range(2):
            store.allow("k", 2, 0.05)
        assert store.allow("k", 2, 0.05)[0] is False
        time.sleep(0.08)
        assert store.allow("k", 2, 0.05)[0] is True

    def test_keys_are_independent(self):
        store = WhatsAppLimitStore()
        for _ in range(3):
            store.allow("a", 3, 3600)
        assert store.allow("a", 3, 3600)[0] is False
        assert store.allow("b", 3, 3600)[0] is True


class TestMarkOnce:
    def test_mark_then_is_marked(self):
        store = WhatsAppLimitStore()
        assert store.is_marked("c", 3600) is False
        store.mark("c", 3600)
        assert store.is_marked("c", 3600) is True

    def test_mark_expires(self):
        store = WhatsAppLimitStore()
        store.mark("c", 0.05)
        assert store.is_marked("c", 0.05) is True
        time.sleep(0.08)
        assert store.is_marked("c", 0.05) is False

    def test_is_marked_does_not_mark(self):
        store = WhatsAppLimitStore()
        assert store.is_marked("c", 3600) is False
        assert store.is_marked("c", 3600) is False  # consulta não marca


class TestSingleton:
    def test_get_returns_same_instance(self):
        assert get_whatsapp_limit_store() is get_whatsapp_limit_store()

    def test_reset_creates_new_instance(self):
        first = get_whatsapp_limit_store()
        reset_whatsapp_limit_store()
        assert get_whatsapp_limit_store() is not first


class TestGatewayCouponCapIntegration:
    """F4.5: o cap 1/conversa do gateway lê/grava no store compartilhado."""

    def test_cap_persists_across_gateway_instances(self):
        from app.application.whatsapp.gateway import MessageGateway

        def make_gateway():
            return MessageGateway(
                conversation_repo=None,
                message_repo=None,
                ai_engine=None,
            )

        g1 = make_gateway()
        conv_key = "wa_acc1_5511999999999"
        ttl = g1._COUPON_OFFER_TTL
        assert ttl == 7200

        # Marca como oferecido (como o gateway faz ao mencionar "cupom")
        g1._limit_store.mark(f"coupon_offer:{conv_key}", ttl)

        # Nova instância (simula restart do backend em memória) ainda vê:
        g2 = make_gateway()
        assert g2._limit_store.is_marked(f"coupon_offer:{conv_key}", ttl) is True

        # Chave de outra conversa não é afetada:
        assert g2._limit_store.is_marked("coupon_offer:wa_acc1_5511888888888", ttl) is False


class TestToolsImplSignupRateIntegration:
    """F4.5: rate limit do auto-cadastro usa o store (3/telefone/hora)."""

    def test_signup_rate_limit_via_store(self, monkeypatch):
        from app.application.ai.tools_impl import AIToolsFactory

        monkeypatch.setattr(AIToolsFactory, "_SIGNUP_RATE_WINDOW", 0.05, raising=False)

        factory = AIToolsFactory(db_session=object())
        for i in range(3):
            assert factory._check_signup_rate("11999990001") is None
        assert factory._check_signup_rate("11999990001") == "RATE_LIMITED_PHONE"
        # Outro telefone não é afetado; IP inócuo sem valor (R1).
        assert factory._check_signup_rate("11999990002") is None

    def test_signup_rate_limit_ip_when_present(self, monkeypatch):
        from app.application.ai.tools_impl import AIToolsFactory

        monkeypatch.setattr(AIToolsFactory, "_SIGNUP_RATE_WINDOW", 0.05, raising=False)

        factory = AIToolsFactory(db_session=object())
        # 5 IPs válidos com telefones distintos (nenhum atinge o limite de phone)
        for i in range(5):
            assert factory._check_signup_rate(f"1199999001{i}", ip="10.0.0.1") is None
        # 6ª tentativa: mesmo IP, phone novo → bloqueio por IP
        assert factory._check_signup_rate("11999990099", ip="10.0.0.1") == "RATE_LIMITED_IP"
