"""F10.1 — Endpoint público de auto-cadastro por convite (página web).

Cobre (TestClient, mesmo padrão de test_coupons.py):
- Fluxo feliz: cadastro via token → cliente criado + cupom BEMVINDO-*
- Token single-use: 2º uso com OUTRO telefone → 409
- Reenvio do MESMO telefone → 200 com o cupom original (resposta perdida)
- Consulta do convite (GET): ok / já usado / inexistente / malformado, sem PII
- Token inexistente → 404
- Consentimento LGPD ausente → 422
- Rate limit por telefone (3/hora) → 429 na 4ª
- Rate limit por IP (5/hora) → 429 na 6ª (R1: aqui o IP funciona)
- Formatador de token (prefixo GF-INV- obrigatório)
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.whatsapp_limits import reset_whatsapp_limit_store


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200
    return res.json()["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _isolated_limit_store():
    """Singleton do rate limit limpo por teste."""
    reset_whatsapp_limit_store()
    yield
    reset_whatsapp_limit_store()


def _generate_invite(client, admin_token, codigo: str) -> str:
    res = client.post("/coupons/generate-invite-token", json={"client_codigo": codigo}, headers=_auth(admin_token))
    assert res.status_code == 200, res.text
    return res.json()["invite_token"]


def _signup_payload(token: str, phone: str = "11988887777") -> dict:
    return {
        "inviteToken": token,
        "name": "Maria Souza",
        "phone": phone,
        "rua": "Rua das Flores",
        "numero": "120",
        "bairro": "Jardim América",
        "lgpdConsent": True,
    }


class TestPublicSignupHappyPath:
    def test_signup_creates_client_and_coupon(self, client, admin_token):
        token = _generate_invite(client, admin_token, "000001")

        res = client.post("/public/referral/signup", json=_signup_payload(token))
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "created"
        assert body["referred_codigo"]
        assert body["coupon_code"].startswith("BEMVINDO-")
        assert body["coupon_value"] > 0
        assert body["coupon_valid_until"]

    def test_signup_without_consent_rejected(self, client, admin_token):
        token = _generate_invite(client, admin_token, "000001")
        payload = _signup_payload(token)
        payload["lgpdConsent"] = False

        res = client.post("/public/referral/signup", json=payload)
        assert res.status_code == 422

    def test_signup_token_wrong_prefix(self, client):
        res = client.post("/public/referral/signup", json=_signup_payload("XXX-outro"))
        assert res.status_code == 422


class TestPublicSignupTokenStates:
    def test_token_single_use_second_attempt_409(self, client, admin_token):
        token = _generate_invite(client, admin_token, "000001")

        first = client.post("/public/referral/signup", json=_signup_payload(token, phone="11900000001"))
        assert first.status_code == 200

        # Mesmo token, OUTRO telefone → 409 single-use (o token não é transferível)
        second = client.post("/public/referral/signup", json=_signup_payload(token, phone="11900000002"))
        assert second.status_code == 409

    def test_unknown_token_404(self, client):
        res = client.post(
            "/public/referral/signup",
            json=_signup_payload("GF-INV-does-not-exist-at-all-000"),
        )
        assert res.status_code == 404


class TestPublicSignupRateLimit:
    def test_phone_limit_three_per_hour(self, client, admin_token):
        # 3 tokens distintos (limites do generate não afetam: pendentes contam
        # e o teste usa clientes diferentes)
        phones = ["11911110001", "11911110001", "11911110001", "11911110001"]
        tokens = [_generate_invite(client, admin_token, f"00000{i}") for i in range(1, 4)]

        for i in range(3):
            res = client.post("/public/referral/signup", json=_signup_payload(tokens[i], phone=phones[i]))
            assert res.status_code == 200, res.text

        # 4ª tentativa com o MESMO telefone (token novo) → 429
        res = client.post("/public/referral/signup", json=_signup_payload(tokens[0], phone=phones[3]))
        assert res.status_code == 429
        assert "telefone" in res.json()["detail"].lower()

    def test_ip_limit_five_per_hour(self, client, admin_token):
        # 5 cadastros com telefones distintos do mesmo IP → ok
        for i in range(5):
            token = _generate_invite(client, admin_token, f"00010{i}")
            res = client.post(
                "/public/referral/signup",
                json=_signup_payload(token, phone=f"1192222000{i}"),
                headers={"X-Forwarded-For": "203.0.113.10"},
            )
            assert res.status_code == 200, res.text

        # 6º cadastro, outro telefone, mesmo IP (via X-Forwarded-For) → 429
        token = _generate_invite(client, admin_token, "000105")
        res = client.post(
            "/public/referral/signup",
            json=_signup_payload(token, phone="11922229999"),
            headers={"X-Forwarded-For": "203.0.113.10"},
        )
        assert res.status_code == 429
        assert "endere" in res.json()["detail"].lower()  # "endereço"


class TestPublicSignupPeek:
    """Consulta pública do convite (F10.6) — usada antes de mostrar o form."""

    def test_pending_invite_is_valid_and_shows_the_offer(self, client, admin_token):
        token = _generate_invite(client, admin_token, "000001")

        res = client.get(f"/public/referral/invite/{token}")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["valid"] is True
        assert body["reason"] == "ok"
        assert body["coupon_value"] > 0
        assert body["validity_days"] > 0

    def test_used_invite_reports_already_used(self, client, admin_token):
        token = _generate_invite(client, admin_token, "000001")
        client.post("/public/referral/signup", json=_signup_payload(token, phone="11966660001"))

        res = client.get(f"/public/referral/invite/{token}")
        assert res.status_code == 200, res.text
        assert res.json()["valid"] is False
        assert res.json()["reason"] == "already_used"

    def test_unknown_and_malformed_tokens(self, client):
        unknown = client.get("/public/referral/invite/GF-INV-nao-existe-mesmo-000")
        assert unknown.status_code == 200
        assert unknown.json()["reason"] == "not_found"

        malformed = client.get("/public/referral/invite/qualquer-coisa")
        assert malformed.status_code == 200
        assert malformed.json()["reason"] == "malformed"

    def test_peek_does_not_leak_referrer_data(self, client, admin_token):
        """Sem PII de terceiros: nada de nome/dados do indicador (LGPD)."""
        token = _generate_invite(client, admin_token, "000001")

        body = client.get(f"/public/referral/invite/{token}").json()
        assert "referrer" not in str(body).lower()
        assert "indicador" not in str(body).lower()
        assert set(body.keys()) == {"valid", "reason", "coupon_value", "coupon_type", "validity_days"}

    def test_peek_rate_limit_per_ip(self, client):
        # 60 consultas do mesmo IP passam; a 61ª é bloqueada
        for _ in range(60):
            assert (
                client.get(
                    "/public/referral/invite/GF-INV-x",
                    headers={"X-Forwarded-For": "198.51.100.7"},
                ).status_code
                == 200
            )

        blocked = client.get(
            "/public/referral/invite/GF-INV-x",
            headers={"X-Forwarded-For": "198.51.100.7"},
        )
        assert blocked.status_code == 429


class TestPublicSignupReplay:
    """Reenvio do próprio indicado — resposta perdida na queda de rede/túnel.

    Sem isto, o reenvio automático da página (F10.5) receberia 409 e o
    cliente perderia o cupom que já tinha sido emitido.
    """

    def test_same_phone_recovers_coupon_instead_of_409(self, client, admin_token):
        token = _generate_invite(client, admin_token, "000002")
        phone = "11955550001"

        first = client.post("/public/referral/signup", json=_signup_payload(token, phone=phone))
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "created"

        # Cliente achou que falhou e reenviou → mesmo cupom, sem erro
        second = client.post("/public/referral/signup", json=_signup_payload(token, phone=phone))
        assert second.status_code == 200, second.text
        body = second.json()
        assert body["status"] == "replayed"
        assert body["coupon_code"] == first.json()["coupon_code"]
        assert body["referred_codigo"] == first.json()["referred_codigo"]
        assert "já estava concluído" in body["message"]

    def test_replay_ignores_phone_formatting(self, client, admin_token):
        """Telefone com máscara é o MESMO telefone (comparação normalizada)."""
        token = _generate_invite(client, admin_token, "000003")

        first = client.post("/public/referral/signup", json=_signup_payload(token, phone="(11) 95555-0002"))
        assert first.status_code == 200, first.text

        second = client.post("/public/referral/signup", json=_signup_payload(token, phone="11955550002"))
        assert second.status_code == 200, second.text
        assert second.json()["coupon_code"] == first.json()["coupon_code"]
        assert second.json()["referred_codigo"] == first.json()["referred_codigo"]


class TestPublicSignupLgpd:
    def test_response_does_not_leak_third_party_data(self, client, admin_token):
        """Resposta só contém dados do PRÓPRIO indicado (LGPD)."""
        token = _generate_invite(client, admin_token, "000001")
        res = client.post("/public/referral/signup", json=_signup_payload(token, phone="11933330001"))
        assert res.status_code == 200
        body = res.json()
        text = str(body).lower()
        # Não menciona o indicador nem dados de terceiros
        assert "referrer" not in text
        assert "indicador" not in text
        # Só o código do cupom do próprio indicado
        assert body["coupon_code"].startswith("BEMVINDO-")
