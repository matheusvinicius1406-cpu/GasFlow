from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

ALGORITHM = "HS256"
ACCESS_TOKEN = "access"
REFRESH_TOKEN = "refresh"

# bcrypt opera sobre no máximo 72 bytes; truncamos para respeitar o limite.
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    payload = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(payload, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, senha_hash: str) -> bool:
    payload = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(payload, senha_hash.encode("utf-8"))
    except ValueError:
        return False


def _create_token(subject: str, token_type: str, expires: timedelta, extra: dict) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires,
        **extra,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: int, company_id: int, role: str) -> str:
    return _create_token(
        subject=str(user_id),
        token_type=ACCESS_TOKEN,
        expires=timedelta(minutes=settings.access_token_expire_minutes),
        extra={"company_id": company_id, "role": role},
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        subject=str(user_id),
        token_type=REFRESH_TOKEN,
        expires=timedelta(days=settings.refresh_token_expire_days),
        extra={},
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise UnauthorizedError("Token inválido ou expirado") from exc

    if payload.get("type") != expected_type:
        raise UnauthorizedError("Tipo de token inválido")

    return payload
