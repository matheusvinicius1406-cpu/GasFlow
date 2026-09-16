"""
Coupon Offer Cap TTL Tests — F4.6

Testa que o cap 1/conversa tem TTL de 2h (7200s).
"""

import inspect
from app.application.whatsapp.gateway import MessageGateway


class TestCouponOfferCapTTL:
    def test_coupon_offer_ttl_is_2h(self):
        """TTL do cap de oferta de cupom deve ser 2h (7200s)."""
        src = inspect.getsource(MessageGateway.__init__)
        assert "_COUPON_OFFER_TTL = 7200" in src
