"""Primitivos de JWT HS256 (stdlib) compartilhados pelos tokens do app.

Estavam embutidos em `driver_mobile_auth` (apresentação). Foram extraídos para
cá para que o token do operador use **exatamente** o mesmo código de assinatura
e verificação: duas implementações de checagem de assinatura é como se abre
espaço para divergência em cima de segurança.

Sem dependência nova: HS256 com `hmac`/`hashlib` da stdlib. As regras da
auditoria de segurança estão preservadas e documentadas em `decode()`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
from datetime import datetime
from typing import Any, Iterable

# Clock skew tolerado na validação de `exp` — o cliente pode estar adiantado ou
# atrasado (leeway ≥ 30s, recomendação da auditoria de segurança).
JWT_CLOCK_SKEW_S = 30

# Fallback usado APENAS fora de produção (testes/dev). Em produção a ausência de
# segredo é erro, nunca silêncio.
DEV_FALLBACK_SECRET = "gasflow-dev-secret"


class TokenError(Exception):
    """Token inválido, expirado ou de escopo errado.

    Carrega a mensagem que a camada de apresentação deve devolver (401), para
    que a aplicação continue sem importar FastAPI.
    """

    def __init__(self, message: str = "Invalid token") -> None:
        super().__init__(message)
        self.message = message


# ── base64url ────────────────────────────────────────────────


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


# ── Segredo ──────────────────────────────────────────────────


def ensure_file_secret(path: str) -> str:
    """Secret estável gerado uma única vez e persistido FORA do repositório.

    Escrita atômica (tmp + replace) para não expor um secret parcialmente
    gravado em caso de crash. Usado como último recurso de configuração em
    desktop/instalação single-machine (o backend empacotado roda no PC do
    depósito, sem orquestração — um arquivo local é aceitável).
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                stored = fh.read().strip()
            if len(stored) >= 32:
                return stored
        except OSError:
            pass  # ilegível/corrompido → regenera
    generated = secrets.token_urlsafe(48)
    tmp_path = f"{path}.{os.getpid()}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        fh.write(generated)
    os.replace(tmp_path, path)
    try:
        os.chmod(path, 0o600)  # POSIX; no-op na prática no Windows
    except OSError:
        pass
    return generated


def resolve_jwt_secret(
    *,
    env_var: str,
    file_env_var: str,
    settings_values: Iterable[str],
    default_file_name: str,
    environment: str = "",
) -> str:
    """Segredo HS256 dedicado a um escopo, sem default hardcoded em produção.

    Ordem de resolução (auditoria de segurança):

      1. variável de ambiente (`env_var`), ≥32 bytes em produção;
      2. valor de settings (`settings_values`), mesma origem via config;
      3. arquivo gerado 1x em `file_env_var` (default:
         ``<tempdir>/gasflow/<default_file_name>``);
      4. fallback de dev APENAS fora de produção.

    Cada escopo tem o **seu** segredo: um token de entregador nunca é assinado
    com a mesma chave do operador.
    """
    env_secret = os.getenv(env_var, "")
    if not env_secret:
        env_secret = next((v for v in settings_values if v), "")
    if env_secret:
        return env_secret

    path = os.getenv(file_env_var) or os.path.join(tempfile.gettempdir(), "gasflow", default_file_name)
    try:
        return ensure_file_secret(path)
    except OSError:
        if environment == "production":
            raise RuntimeError(
                f"{env_var} ou {file_env_var} é obrigatório em produção (mínimo 32 bytes aleatórios)."
            ) from None
        return DEV_FALLBACK_SECRET


# ── encode / decode ──────────────────────────────────────────


def encode(payload: dict[str, Any], secret: str) -> str:
    """Assina `payload` como JWT HS256 (header mínimo + payload compacto)."""
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = (
        b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + b64url(json.dumps(payload, separators=(",", ":")).encode())
    )
    signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + b64url(signature)


def encode_with_now(payload: dict[str, Any], secret: str, expires_seconds: int) -> str:
    """`encode` com `iat`/`exp` preenchidos a partir de agora (UTC)."""
    now = int(datetime.utcnow().timestamp())
    full = {**payload, "iat": now, "exp": now + expires_seconds}
    return encode(full, secret)


def decode(token: str, secret: str, *, expected_scope: str) -> dict[str, Any]:
    """Verifica header, assinatura, `exp` (com leeway) e escopo.

    Regras da auditoria de segurança, todas explícitas:

    - header com `alg` diferente de HS256 → erro ("alg: none" e confusão de
      algoritmo são rejeitados, nunca tratados como token sem assinatura);
    - assinatura comparada com `hmac.compare_digest` (timing-safe);
    - `exp` é obrigatório e numérico — token sem `exp` nunca é aceito;
    - `scope` precisa bater com o do emissor.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("Invalid token")
    try:
        header = json.loads(b64url_decode(parts[0]))
        payload = json.loads(b64url_decode(parts[1]))
    except ValueError as exc:
        raise TokenError("Invalid token") from exc
    if not isinstance(header, dict) or header.get("alg") != "HS256":
        raise TokenError("Invalid token")

    signing_input = parts[0] + "." + parts[1]
    expected = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(b64url(expected), parts[2]):
        raise TokenError("Invalid token")

    if not isinstance(payload, dict):
        raise TokenError("Invalid token")
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or exp < datetime.utcnow().timestamp() - JWT_CLOCK_SKEW_S:
        raise TokenError("Token expired")
    if payload.get("scope") != expected_scope:
        raise TokenError("Invalid token scope")
    return payload
