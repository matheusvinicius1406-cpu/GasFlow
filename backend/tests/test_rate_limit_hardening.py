"""Hardening de segurança do rate limit e dos docs públicos.

- Chave do bucket: hash do Bearer token (nunca token cru em chave de Redis
  nem em log).
- X-Forwarded-For só é honrado com RATE_LIMIT_TRUST_PROXY=1 (default OFF —
  fora de proxy, o cliente escreveria o próprio IP e escolheria o bucket).
- Swagger/ReDoc/OpenAPI: ligados fora de produção, desligados com
  ENVIRONMENT=production, e DOCS_ENABLED é autoridade em ambos os lados.
"""

import os

from starlette.requests import Request

from app.core.config import env_flag, settings
from app.core.rate_limit import _client_id


def _req(headers=None, client=("10.0.0.1", 40000)) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/clients",
        "raw_path": b"/clients",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": client,
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


class TestChaveDoBucket:
    def test_token_nunca_fica_cru_na_chave(self):
        token = "hf_" + "x" * 34
        chave = _client_id(_req({"Authorization": f"Bearer {token}"}))
        assert token not in chave
        assert token[:10] not in chave
        assert chave.startswith("tok:")

    def test_mesmo_token_mesmo_bucket_tokens_diferentes_buckets_diferentes(self):
        def chave(token: str) -> str:
            return _client_id(_req({"Authorization": f"Bearer {token}"}))

        assert chave("token-aaa") == chave("token-aaa")
        assert chave("token-aaa") != chave("token-bbb")

    def test_sem_token_usa_ip(self):
        assert _client_id(_req()) == "10.0.0.1"
        assert _client_id(_req(client=None)) == "unknown"

    def test_xff_ignorado_por_padrao(self):
        # Atacante escolheria o IP e fugiria do rate limit.
        req = _req({"X-Forwarded-For": "9.9.9.9"})
        assert settings.rate_limit_trust_proxy is False
        assert _client_id(req) == "10.0.0.1"

    def test_xff_honrado_quando_confia_no_proxy(self, monkeypatch):
        monkeypatch.setattr(settings, "rate_limit_trust_proxy", True, raising=False)
        req = _req({"X-Forwarded-For": "9.9.9.9, 8.8.8.8"})
        assert _client_id(req) == "xff:9.9.9.9"

    def test_xff_vazio_cai_no_ip(self, monkeypatch):
        monkeypatch.setattr(settings, "rate_limit_trust_proxy", True, raising=False)
        assert _client_id(_req()) == "10.0.0.1"


class TestEnvFlag:
    def test_ausente_usa_default(self, monkeypatch):
        monkeypatch.delenv("FLAG_TESTE", raising=False)
        assert env_flag("FLAG_TESTE", True) is True
        assert env_flag("FLAG_TESTE", False) is False

    def test_ligada_desligada(self, monkeypatch):
        for valor in ("1", "true", "TRUE", "on", "yes"):
            monkeypatch.setenv("FLAG_TESTE", valor)
            assert env_flag("FLAG_TESTE", False) is True, valor
        for valor in ("0", "false", "off", "no"):
            monkeypatch.setenv("FLAG_TESTE", valor)
            assert env_flag("FLAG_TESTE", True) is False, valor
        # Vazia conta como ausente (default).
        monkeypatch.setenv("FLAG_TESTE", "")
        assert env_flag("FLAG_TESTE", True) is True

    def test_default_liga_docs_fora_de_producao(self, monkeypatch):
        # Reavalia a MESMA expressão do campo docs_enabled do Settings.
        def _default():
            return env_flag("DOCS_ENABLED", os.getenv("ENVIRONMENT", "development") != "production")

        monkeypatch.delenv("DOCS_ENABLED", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")
        assert _default() is True
        monkeypatch.setenv("ENVIRONMENT", "production")
        assert _default() is False
        monkeypatch.setenv("DOCS_ENABLED", "1")
        assert _default() is True  # produção, mas DOCS_ENABLED força abrir
        monkeypatch.setenv("DOCS_ENABLED", "0")
        monkeypatch.setenv("ENVIRONMENT", "development")
        assert _default() is False  # dev, mas DOCS_ENABLED=0 fecha
