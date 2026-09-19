"""
Coupon Offer Cap TTL Tests — F4.6 / F4.5

Testa que o cap 1/conversa tem TTL de 2h (7200s) e usa o store TTL
compartilhado (Redis quando RATE_LIMIT_MODE=redis, fallback memória).
"""

import inspect
from app.application.whatsapp import gateway as gw
from app.application.whatsapp.gateway import MessageGateway


class TestCouponOfferCapTTL:
    def test_coupon_offer_ttl_is_2h(self):
        """TTL do cap de oferta de cupom deve ser 2h (7200s)."""
        src = inspect.getsource(MessageGateway.__init__)
        assert "_COUPON_OFFER_TTL = 7200" in src

    def test_gateway_uses_shared_limit_store(self):
        """F4.5: cap persiste via WhatsAppLimitStore (Redis opcional)."""
        src = inspect.getsource(MessageGateway.__init__)
        assert "get_whatsapp_limit_store()" in src
        assert "coupon_offer:" in inspect.getsource(gw)
