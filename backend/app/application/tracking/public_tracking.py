"""Token de rastreio público (Parte 1 — fixes 3 e 4).

Stateless — **nenhuma tabela nova**. O token é um HMAC-SHA256 (base64url) sobre
um payload com escopo mínimo: tenant + driver + expiração + **epoch**.

Correções desta versão:

3. **Teto de TTL.** Antes o emissor aceitava qualquer `ttl_seconds`; agora o
   limite é `MAX_TTL_S` (24 h) e o endpoint rejeita acima disso com 422.
4. **Revogação.** O token embute a `tracking_epoch` vigente do entregador. Se o
   admin revoga (incrementa a epoch em `delivery_drivers.tracking_epoch`), todo
   link já emitido deixa de valer — o snapshot responde **410 Gone**, que é
   semanticamente correto: o link existiu e foi revogado (não é 401 de link
   inválido).

Segredo **dedicado** ao escopo (`PUBLIC_TRACKING_SECRET`) — um token público
nunca é assinado com a chave do operador (nem o contrário).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional

from app.application.security.jwt_crypto import resolve_jwt_secret
from app.core.config import settings

PUBLIC_TRACKING_SCOPE = "public_tracking"
DEFAULT_TTL_S = 6 * 3600
#: Teto duro do link público (24 h) — um link "para sempre" é um vazamento.
MAX_TTL_S = 86400


def public_tracking_secret() -> str:
    """Segredo HS256 dedicado ao link público."""
    return resolve_jwt_secret(
        env_var="PUBLIC_TRACKING_SECRET",
        file_env_var="PUBLIC_TRACKING_SECRET_FILE",
        settings_values=(),
        default_file_name="public_tracking_secret.key",
        environment=settings.environment,
    )


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(body: str) -> str:
    return _b64e(hmac.new(public_tracking_secret().encode(), body.encode(), hashlib.sha256).digest())


def issue_public_tracking_token(
    *,
    tenant_id: str,
    driver_id: str,
    ttl_seconds: int = DEFAULT_TTL_S,
    epoch: int = 0,
) -> str:
    """Emite o token do link público (uso: operador/admin).

    `epoch` é a `delivery_drivers.tracking_epoch` do momento da emissão: é o que
    permite revogar depois.
    """
    ttl = max(1, min(int(ttl_seconds), MAX_TTL_S))
    payload = {
        "t": tenant_id,
        "d": driver_id,
        "e": int(epoch),
        "exp": int(time.time()) + ttl,
        "scope": PUBLIC_TRACKING_SCOPE,
    }
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    return f"{body}.{_sign(body)}"


def verify_public_tracking_token(token: str) -> Optional[Dict[str, Any]]:
    """Valida assinatura, escopo e expiração. `None` para qualquer token ruim.

    O payload devolvido inclui `e` (epoch) — quem chama compara com a epoch
    atual do entregador para decidir entre válido e revogado.
    """
    if not token or "." not in token:
        return None
    body, _, signature = token.partition(".")
    if not hmac.compare_digest(signature, _sign(body)):
        return None
    try:
        payload = json.loads(_b64d(body))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("scope") != PUBLIC_TRACKING_SCOPE:
        return None
    try:
        expired = int(payload.get("exp", 0)) < int(time.time())
        payload["e"] = int(payload.get("e", 0))
    except (TypeError, ValueError):
        return None
    if expired or not payload.get("t") or not payload.get("d"):
        return None
    return payload
