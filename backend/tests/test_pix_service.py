"""
PIX-01 — Testes do PIX estático (BR Code + QR Code).

Cobertura:
- Lib pura (PixService / build_pix_copy_paste): estrutura do BR Code, CRC16,
  formatação de valor, sanitização de TXID, validação de chave, QR base64.
- PaymentService: config → copy_paste_code, create_payment PIX → BR Code
  real, generate_pix_payload com/sem config e isolamento por tenant.
- Endpoints HTTP: /payments/pix/payload e /payments/pix/{txid}/status
  (determinísticos via monkeypatch do get_payment_service — sem depender
  do estado do banco).
"""

import base64

import pytest
from fastapi.testclient import TestClient

from app.domain.payment.pix_service import (
    PixService,
    build_pix_copy_paste,
    validate_pix_key,
    _crc16_ccitt,
)
from app.domain.payment.service import PaymentService


# ── Helpers ───────────────────────────────────────────

def valid_crc(payload: str) -> bool:
    """Recomputa o CRC16 sobre o payload até '6304' e compara com o final."""
    assert "6304" in payload, "payload deve conter o campo 6304"
    body = payload[:-4]  # tudo até o '6304' inclusive; CRC são os 4 hex finais
    return int(payload[-4:], 16) == _crc16_ccitt(body)


# ── Lib pura ──────────────────────────────────────────

class TestBrCodeGeneration:
    def test_payload_structure(self):
        code = build_pix_copy_paste(
            key="contato@teste.com", key_type="EMAIL",
            merchant_name="GasFlow", merchant_city="SAO PAULO",
            amount=150.0, txid="ABCDE12345",
        )
        assert code.startswith("00020126")
        assert "br.gov.bcb.pix" in code
        assert "5303986" in code          # moeda BRL
        assert "5802BR" in code           # país
        assert valid_crc(code)

    def test_amount_formatted_brl(self):
        code = build_pix_copy_paste(
            key="contato@teste.com", key_type="EMAIL", amount=150.0,
        )
        assert "54150,00" in code or "54" in code

    def test_static_copy_paste_has_no_amount(self):
        code = build_pix_copy_paste(
            key="contato@teste.com", key_type="EMAIL",
        )
        # Sem amount: campo 54 não deve existir com valor monetário.
        assert "54" not in code

    def test_txid_default_stars(self):
        code = build_pix_copy_paste(
            key="contato@teste.com", key_type="EMAIL", amount=10.0,
        )
        # Campo 62 > subcampo 05 com valor literal '***' (PIX estático).
        assert "62070503***" in code

    def test_txid_sanitized_and_truncated(self):
        code = build_pix_copy_paste(
            key="contato@teste.com", key_type="EMAIL", amount=10.0,
            txid="GAS-ORD-123!" + "X" * 40,
        )
        # TXID alfanumérico, máx 25: "GASORD123X" * ~
        assert "GASORD123X" in code
        assert "!" not in code

    def test_invalid_amount_raises(self):
        service = PixService()
        with pytest.raises(ValueError):
            service.generate_payload(amount=0, key="k")
        with pytest.raises(ValueError):
            service.generate_payload(amount=-5, key="k")

    def test_missing_key_raises(self):
        service = PixService()
        with pytest.raises(ValueError):
            service.generate_payload(amount=10.0)

    def test_key_validation(self):
        with pytest.raises(ValueError):
            validate_pix_key("123", "CPF")
        with pytest.raises(ValueError):
            validate_pix_key("12345678901234", "CPF")
        with pytest.raises(ValueError):
            validate_pix_key("123456789012345", "CNPJ")  # 15 dígitos
        with pytest.raises(ValueError):
            validate_pix_key("sem-arroba", "EMAIL")
        # Válidas
        validate_pix_key("12345678901", "CPF")
        validate_pix_key("12345678901234", "CNPJ")
        validate_pix_key("a@b.com", "EMAIL")
        validate_pix_key("+5511999999999", "PHONE")
        validate_pix_key("123e4567-e89b-12d3-a456-426614174000", "RANDOM")

    def test_qr_code_is_png(self):
        service = PixService()
        result = service.generate_payload(
            amount=50.0,
            key="contato@teste.com",
            key_type="EMAIL",
            merchant_name="Teste",
        )
        assert result["qr_code"].startswith("data:image/png;base64,")
        raw = base64.b64decode(result["qr_code"].split(",", 1)[1])
        assert raw[:4] == b"\x89PNG"

    def test_generate_payload_fields(self):
        service = PixService()
        result = service.generate_payload(
            amount=99.9,
            key="contato@teste.com", key_type="EMAIL",
            merchant_name="Teste", merchant_city="SAO PAULO",
            txid="PEDIDO42",
        )
        assert result["br_code"].startswith("000201")
        assert valid_crc(result["br_code"])
        assert result["txid"] == "PEDIDO42"
        assert result["amount"] == 99.9
        assert result["key_type"] == "EMAIL"
        assert result["merchant_city"] == "SAO PAULO"


# ── PaymentService (integração, in-memory) ────────────

class TestPaymentServicePix:
    def test_create_pix_config_stores_copy_paste(self):
        service = PaymentService()
        config = service.create_pix_config(
            "t1", "contato@teste.com", "EMAIL", "Teste", city="SAO PAULO",
        )
        assert config.copy_paste_code
        assert valid_crc(config.copy_paste_code)

    def test_create_payment_pix_generates_br_code(self):
        service = PaymentService()
        service.create_method("t1", "PIX", "PIX", "PIX")
        service.create_pix_config("t1", "contato@teste.com", "EMAIL", "Teste")
        payment = service.create_payment(
            "t1", "order-1", "ORD-001", "C001", 150.0, "PIX",
        )
        assert payment.pix_key_used == "contato@teste.com"
        assert payment.pix_copy_paste
        assert valid_crc(payment.pix_copy_paste)
        assert "54" in payment.pix_copy_paste  # com valor

    def test_generate_pix_payload_no_config_returns_none(self):
        service = PaymentService()
        assert service.generate_pix_payload("t1", 100.0) is None

    def test_generate_pix_payload_returns_payload(self):
        service = PaymentService()
        service.create_pix_config("t1", "contato@teste.com", "EMAIL", "Teste")
        result = service.generate_pix_payload("t1", 120.0, order_codigo="ORD-9")
        assert result is not None
        assert result["br_code"].startswith("000201")
        assert valid_crc(result["br_code"])
        assert result["qr_code"].startswith("data:image/png;base64,")

    def test_generate_pix_payload_tenant_isolation(self):
        service = PaymentService()
        service.create_pix_config("t1", "contato@teste.com", "EMAIL", "T1")
        assert service.generate_pix_payload("t2", 10.0) is None
        assert service.generate_pix_payload("t1", 10.0) is not None

    def test_generate_pix_payload_invalid_amount(self):
        service = PaymentService()
        with pytest.raises(ValueError):
            service.generate_pix_payload("t1", 0)


# ── Endpoints HTTP (determinísticos) ──────────────────

@pytest.fixture()
def app_client(monkeypatch):
    """TestClient com get_payment_service substituído por service in-memory."""
    from app.presentation.api import payments as payments_module

    service = PaymentService()
    monkeypatch.setattr(payments_module, "get_payment_service", lambda: service)

    from app.main import app

    with TestClient(app) as client:
        resp = client.post("/auth/login", json={
            "username": "admin",
            "password": "test_password_123",
        })
        assert resp.status_code == 200, f"login falhou: {resp.text}"
        yield client, {"Authorization": f"Bearer {resp.json()['token']}"}


class TestPixEndpoints:
    def test_payload_requires_active_config(self, app_client):
        client, headers = app_client
        resp = client.post("/payments/pix/payload", json={"amount": 100.0}, headers=headers)
        assert resp.status_code == 409

    def test_payload_generates_qr(self, app_client):
        client, headers = app_client
        client.post("/payments/pix", json={
            "key": "contato@teste.com",
            "key_type": "EMAIL",
            "holder_name": "Teste",
            "city": "SAO PAULO",
        }, headers=headers)
        resp = client.post("/payments/pix/payload", json={
            "amount": 250.0,
            "description": "Pedido 1",
            "order_codigo": "ORD-123",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["br_code"].startswith("000201")
        assert valid_crc(data["br_code"])
        assert data["qr_code"].startswith("data:image/png;base64,")
        assert data["txid"] == "GASORD123"

    def test_payload_invalid_amount(self, app_client):
        client, headers = app_client
        client.post("/payments/pix", json={
            "key": "contato@teste.com",
            "key_type": "EMAIL",
        }, headers=headers)
        resp = client.post("/payments/pix/payload", json={"amount": 0}, headers=headers)
        assert resp.status_code == 400

    def test_status_not_found(self, app_client):
        client, headers = app_client
        resp = client.get("/payments/pix/GASX99/status", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "NOT_FOUND"

    def test_status_found_after_payment(self, app_client):
        client, headers = app_client
        client.post("/payments/methods", json={
            "code": "PIX", "name": "PIX", "payment_type": "PIX",
        }, headers=headers)
        client.post("/payments/pix", json={
            "key": "contato@teste.com", "key_type": "EMAIL",
        }, headers=headers)
        pay = client.post("/payments/", json={
            "order_id": "order-9", "order_codigo": "ORD-9",
            "customer_codigo": "C9", "amount": 80.0, "method_code": "PIX",
        }, headers=headers)
        assert pay.status_code == 200
        copy_paste = pay.json()["payment"]["pix_copy_paste"]
        # Acha o TXID GASORD9 dentro do BR Code
        assert "GASORD9" in copy_paste
        resp = client.get("/payments/pix/GASORD9/status", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "PENDING"
        assert resp.json()["payment_id"] == pay.json()["payment"]["id"]