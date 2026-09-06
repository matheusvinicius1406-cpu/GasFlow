"""
PIX PSP Gateway — abstraction over payment service providers (banks).

Status das pendências PIX-01: o payload BR Code + QR é gerado localmente; o
que faltava era a camada de PSP para (a) registrar o pagamento no provedor e
(b) receber a confirmação via webhook e confirmar o Payment automaticamente.

Providers:
- mock (default): sem rede — simula o ciclo PENDING → CONFIRMED. Usado em
  dev/testes e enquanto nenhuma credencial real está configurada.
- gerencianet | pagseguro | mercadopago: adapters HTTP reais. Exigem
  PSP_API_URL + PSP_API_KEY (e PSP_CLIENT_ID/SECRET quando o provedor usar
  OAuth). Sem credenciais, qualquer chamada levanta PspNotConfigured — nada
  de tentar rede com configuração incompleta.

Segurança do webhook: assinatura HMAC-SHA256 do corpo cru com
PSP_WEBHOOK_SECRET (header X-Pix-Signature). Sem secret configurado o
endpoint responde 503 (nunca aceita confirmação não assinada).
"""

import hashlib
import hmac
import logging
from typing import Any, Dict

from app.core.config import settings

logger = logging.getLogger("gasflow.payments.psp")


class PspError(Exception):
    """Base error for PSP operations."""


class PspNotConfigured(PspError):
    """Raised when a real PSP is selected but its credentials are missing."""


class PspProvider:
    """Interface for a PSP provider (mock or real)."""

    name = "base"

    async def create_pix(
        self,
        amount: float,
        txid: str,
        description: str = "",
        key: str = "",
        merchant_name: str = "GasFlow",
        merchant_city: str = "SAO PAULO",
        webhook_url: str = "",
    ) -> Dict[str, Any]:
        raise NotImplementedError

    async def get_status(self, txid: str) -> Dict[str, Any]:
        raise NotImplementedError


class MockPixProvider(PspProvider):
    """No-network provider: records payments and simulates confirmation.

    ``simulate_confirmation(txid)`` flips a recorded payment to CONFIRMED —
    used by dev tooling and tests to exercise the webhook path without a
    real bank.
    """

    name = "mock"

    def __init__(self):
        self._payments: Dict[str, Dict[str, Any]] = {}

    async def create_pix(
        self,
        amount: float,
        txid: str,
        description: str = "",
        key: str = "",
        merchant_name: str = "GasFlow",
        merchant_city: str = "SAO PAULO",
        webhook_url: str = "",
    ) -> Dict[str, Any]:
        record = {
            "psp_txid": txid,
            "external_id": txid,
            "status": "PENDING",
            "amount": amount,
            "provider": self.name,
            "description": description,
            "created_at": None,
        }
        self._payments[txid] = record
        return dict(record)

    async def get_status(self, txid: str) -> Dict[str, Any]:
        record = self._payments.get(txid)
        if record is None:
            return {"psp_txid": txid, "status": "NOT_FOUND", "provider": self.name}
        return dict(record)

    async def simulate_confirmation(self, txid: str) -> Dict[str, Any]:
        """Simulate the bank confirming the payment (dev/test only)."""
        record = self._payments.get(txid)
        if record is None:
            raise PspError(f"Unknown PIX txid: {txid}")
        record["status"] = "CONFIRMED"
        return dict(record)


class HttpPixProvider(PspProvider):
    """Real PSP adapter over HTTPS.

    The wire contract (path `/pix`, `/pix/{txid}`, body fields) is the common
    shape used by Gerencianet/PagSeguro/Mercado Pago-style APIs. Concrete
    providers may override ``_headers``/``_payload`` — kept minimal until a
    specific provider is validated with real credentials.
    """

    name = "http"

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        client_id: str = "",
        client_secret: str = "",
        provider: str = "gerencianet",
    ):
        self.provider_name = provider
        self.api_url = (api_url or "").rstrip("/")
        self.api_key = api_key
        self.client_id = client_id
        self.client_secret = client_secret

    def _require_credentials(self):
        if not self.api_url or not self.api_key:
            raise PspNotConfigured(f"PSP '{self.provider_name}' requires PSP_API_URL and PSP_API_KEY")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def _post(self, path: str, payload: dict) -> Dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.api_url}{path}", json=payload, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def _get(self, path: str) -> Dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.api_url}{path}", headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def create_pix(
        self,
        amount: float,
        txid: str,
        description: str = "",
        key: str = "",
        merchant_name: str = "GasFlow",
        merchant_city: str = "SAO PAULO",
        webhook_url: str = "",
    ) -> Dict[str, Any]:
        self._require_credentials()
        body = {
            "amount": amount,
            "txid": txid,
            "description": description,
            "key": key,
            "merchant_name": merchant_name,
            "merchant_city": merchant_city,
            "webhook_url": webhook_url,
        }
        result = await self._post("/pix", body)
        result.setdefault("provider", self.provider_name)
        result.setdefault("psp_txid", txid)
        return result

    async def get_status(self, txid: str) -> Dict[str, Any]:
        self._require_credentials()
        result = await self._get(f"/pix/{txid}")
        result.setdefault("provider", self.provider_name)
        result.setdefault("psp_txid", txid)
        return result


# ── Signature helpers (webhook) ─────────────────────────


def compute_webhook_signature(body: bytes, secret: str) -> str:
    """HMAC-SHA256 hex digest of the raw body using the shared secret."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    """Constant-time signature verification for PSP webhook calls."""
    if not secret or not signature:
        return False
    expected = compute_webhook_signature(body, secret)
    return hmac.compare_digest(expected, signature.lower())


# ── Factory ─────────────────────────────────────────────

_PROVIDER_ALIASES = {
    "gerencianet": "http",
    "pagseguro": "http",
    "mercadopago": "http",
}


def create_psp_gateway() -> PspProvider:
    """Build the PSP provider from settings (PSP_PROVIDER + PSP_* envs)."""
    provider = (settings.psp_provider or "mock").lower()
    if provider == "mock":
        return MockPixProvider()
    if provider in _PROVIDER_ALIASES:
        return HttpPixProvider(
            api_url=settings.psp_api_url,
            api_key=settings.psp_api_key,
            client_id=settings.psp_client_id,
            client_secret=settings.psp_client_secret,
            provider=provider,
        )
    raise PspNotConfigured(f"Unknown PSP_PROVIDER: {provider}")
