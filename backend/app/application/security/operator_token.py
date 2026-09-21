"""Tokens do operador (B5): access JWT curto + refresh rotativo.

Mesmo desenho já aprovado no app do entregador
(`presentation/api/logistics/driver_mobile_auth.py`) — o que muda é o escopo e
o segredo, que é **dedicado** (um token do entregador nunca é assinado com a
chave do console, e vice-versa):

- **access**: JWT HS256 de 15 min, escopo `operator`, carregando o `sid` da
  sessão. Curto porque trafega em toda request: se vazar, vale pouco.
- **refresh**: opaco e aleatório (nunca JWT), gravado apenas como sha256 na
  linha da sessão e **rotacionado a cada uso**. Reuso de um refresh já
  rotacionado revoga a sessão inteira (família morta) — o mesmo sinal de
  comprometimento que o fluxo mobile já detecta.

Detalhe que importa para segurança: o JWT **não** é stateless de verdade. Ele
carrega o `sid` e `AuthService.validate_token` lê a linha da sessão, então
revogar sessão mata o acesso na hora — coisa que um JWT puro não faria até
expirar.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict

from app.application.security.jwt_crypto import TokenError, decode, encode_with_now, resolve_jwt_secret
from app.core.config import settings

OPERATOR_SCOPE = "operator"

# Access curto: é o token que trafega em toda request do console.
ACCESS_TTL_MINUTES = 15
# Refresh longo: é o que sustenta a sessão multimodal (desktop + mobile).
REFRESH_TTL_DAYS = 7

PLATFORM_DESKTOP = "desktop"
PLATFORM_MOBILE = "mobile"
VALID_PLATFORMS = (PLATFORM_DESKTOP, PLATFORM_MOBILE)


def operator_jwt_secret() -> str:
    """Segredo HS256 dedicado do operador (nunca o do mobile)."""
    return resolve_jwt_secret(
        env_var="OPERATOR_JWT_SECRET",
        file_env_var="OPERATOR_JWT_SECRET_FILE",
        settings_values=(settings.operator_jwt_secret,),
        default_file_name="operator_jwt_secret.key",
        environment=settings.environment,
    )


def issue_access_token(
    *,
    user_id: str,
    tenant_id: str,
    session_id: str,
    role: str,
    platform: str = PLATFORM_DESKTOP,
    expires_minutes: int = ACCESS_TTL_MINUTES,
) -> str:
    """JWT de acesso do operador, preso a uma sessão (`sid`)."""
    return encode_with_now(
        {
            "sub": user_id,
            "tenant_id": tenant_id,
            "sid": session_id,
            "role": role,
            "scope": OPERATOR_SCOPE,
            "platform": platform,
            "jti": str(uuid.uuid4()),
        },
        operator_jwt_secret(),
        expires_seconds=expires_minutes * 60,
    )


def verify_access_token(token: str) -> Dict[str, Any]:
    """Verifica assinatura, `exp` e escopo do access.

    Levanta `TokenError` (a camada de apresentação traduz para 401) — em
    especial `Invalid token scope` quando alguém tenta usar um token do app do
    entregador no console.
    """
    return decode(token, operator_jwt_secret(), expected_scope=OPERATOR_SCOPE)


def looks_like_jwt(token: str) -> bool:
    """Três partes separadas por ponto = candidato a JWT.

    É o que permite `validate_token` decidir o caminho sem adivinhar: token
    opaco emitido antes do B5 (ou por um serviço) não tem essa forma, e segue
    pelo caminho antigo até expirar.
    """
    return token.count(".") == 2


def generate_refresh_token() -> str:
    """Refresh opaco (nunca JWT) — alta entropia, sem estrutura adivinhável."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """sha256 do refresh. Só o hash vai ao banco; o claro nunca é gravado."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_expiry(days: int = REFRESH_TTL_DAYS) -> datetime:
    """Quando o refresh morre, independente do access."""
    return datetime.utcnow() + timedelta(days=days)


__all__ = [
    "ACCESS_TTL_MINUTES",
    "OPERATOR_SCOPE",
    "PLATFORM_DESKTOP",
    "PLATFORM_MOBILE",
    "REFRESH_TTL_DAYS",
    "VALID_PLATFORMS",
    "TokenError",
    "generate_refresh_token",
    "hash_refresh_token",
    "issue_access_token",
    "looks_like_jwt",
    "operator_jwt_secret",
    "refresh_expiry",
    "verify_access_token",
]
