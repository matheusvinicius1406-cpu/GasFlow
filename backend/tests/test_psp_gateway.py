"""PIX PSP — gateway + webhook tests.

Deterministic: mock provider (no network), signature helpers, factory
selection, and the /payments/webhook/pix endpoint via TestClient with a
DB-less PaymentService (in-memory) injected.
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.payment.models import PaymentStatus
from app.domain.payment.service import PaymentService
from app.infrastructure.payment.psp_gateway import (
    HttpPixProvider,
    MockPixProvider,
    PspNotConfigured,
    compute_webhook_signature,
    create_psp_gateway,
    verify_webhook_signature,
)
from app.presentation.api.payments import router as payments_router


# ── Gateway unit tests ─────────────────────────────────

@pytest.mark.asyncio
async def test_mock_provider_lifecycle():
    provider = MockPixProvider()
    created = await provider.create_pix(
        amount=100.0, txid="GASTEST1", key="test@key", description="Pedido 1"
    )
    assert created["status"] == "PENDING"
    assert created["external_id"] == "GASTEST1"

    status = await provider.get_status("GASTEST1")
    assert status["status"] == "PENDING"

    await provider.simulate_confirmation("GASTEST1")
    assert (await provider.get_status("GASTEST1"))["status"] == "CONFIRMED"

    assert (await provider.get_status("UNKNOWN"))["status"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_http_provider_requires_credentials():
    provider = HttpPixProvider()  # no credentials
    with pytest.raises(PspNotConfigured):
        await provider.create_pix(amount=1.0, txid="X")
    with pytest.raises(PspNotConfigured):
        await provider.get_status("X")

    provider = HttpPixProvider(api_url="https://api.example.com",
                               api_key="k", provider="gerencianet")
    # Credentials present — would attempt HTTP (no network in tests).
    assert provider.api_url == "https://api.example.com"
    assert provider.provider_name == "gerencianet"


def test_factory_selects_mock_by_default(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "psp_provider", "mock")
    assert isinstance(create_psp_gateway(), MockPixProvider)


def test_factory_selects_http_for_real_providers(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "psp_provider", "gerencianet")
    monkeypatch.setattr(settings, "psp_api_url", "https://api.gerencianet.com.br/v1")
    monkeypatch.setattr(settings, "psp_api_key", "secret")
    gateway = create_psp_gateway()
    assert isinstance(gateway, HttpPixProvider)
    assert gateway.provider_name == "gerencianet"

    # Missing credentials → clean PspNotConfigured on use, not a network attempt.
    monkeypatch.setattr(settings, "psp_api_url", "")
    gateway = create_psp_gateway()
    import asyncio

    with pytest.raises(PspNotConfigured):
        asyncio.run(gateway.create_pix(amount=1.0, txid="X"))


def test_factory_rejects_unknown_provider(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "psp_provider", "banco-do-nada")
    with pytest.raises(PspNotConfigured):
        create_psp_gateway()


# ── Signature helpers ──────────────────────────────────

def test_signature_roundtrip():
    body = json.dumps({"txid": "GAS000001", "status": "CONFIRMED"}).encode()
    sig = compute_webhook_signature(body, "segredo")
    assert verify_webhook_signature(body, sig, "segredo") is True
    assert verify_webhook_signature(body, sig.upper(), "segredo") is True
    assert verify_webhook_signature(body, sig, "outro-segredo") is False
    assert verify_webhook_signature(b"{}", sig, "segredo") is False
    assert verify_webhook_signature(body, "", "segredo") is False
    assert verify_webhook_signature(body, sig, "") is False


# ── Webhook endpoint ───────────────────────────────────

import app.presentation.api.payments as payments_module


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(payments_router)
    return TestClient(app)


def _new_service() -> PaymentService:
    return PaymentService(db=None)  # in-memory mode


def _inject_service(monkeypatch, service: PaymentService):
    # The route calls get_payment_service() directly (not via Depends), so we
    # patch the binding inside the payments module.
    monkeypatch.setattr(payments_module, "get_payment_service", lambda: service)


def _create_pix_payment(service: PaymentService, txid: str):
    """Create a PENDING PIX payment whose external_id is the txid."""
    return service.create_payment(
        tenant_id="t1", order_id="ord-1", order_codigo="000001",
        customer_codigo="000001", amount=150.0, method_code="PIX",
        external_id=txid,
    )


def test_webhook_requires_secret(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "psp_webhook_secret", "")
    _inject_service(monkeypatch, _new_service())
    client = _make_client()
    r = client.post("/payments/webhook/pix", json={"txid": "X"})
    assert r.status_code == 503


def test_webhook_rejects_bad_signature(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "psp_webhook_secret", "segredo")
    _inject_service(monkeypatch, _new_service())
    client = _make_client()
    body = json.dumps({"txid": "GASX", "status": "CONFIRMED"})
    r = client.post(
        "/payments/webhook/pix",
        content=body,
        headers={"X-Pix-Signature": "deadbeef"},
    )
    assert r.status_code == 401


def test_webhook_confirms_pending_payment(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "psp_webhook_secret", "segredo")
    service = _new_service()
    payment = _create_pix_payment(service, "GASTX1")
    assert payment.status == PaymentStatus.PENDING
    _inject_service(monkeypatch, service)

    client = _make_client()
    body = json.dumps({"txid": "GASTX1", "status": "CONFIRMED"}).encode()
    sig = compute_webhook_signature(body, "segredo")
    r = client.post(
        "/payments/webhook/pix",
        content=body,
        headers={"X-Pix-Signature": sig},
    )
    assert r.status_code == 200
    assert r.json()["success"] is True

    updated = service.get_payment(payment.id, "t1")
    assert updated.status == PaymentStatus.CONFIRMED
    assert updated.confirmed_by == "psp-webhook"


def test_webhook_unknown_txid_returns_not_found(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "psp_webhook_secret", "segredo")
    _inject_service(monkeypatch, _new_service())
    client = _make_client()
    body = json.dumps({"txid": "NAO-EXISTE"}).encode()
    sig = compute_webhook_signature(body, "segredo")
    r = client.post(
        "/payments/webhook/pix",
        content=body,
        headers={"X-Pix-Signature": sig},
    )
    assert r.status_code == 200
    assert r.json() == {"success": False, "reason": "NOT_FOUND", "txid": "NAO-EXISTE"}
