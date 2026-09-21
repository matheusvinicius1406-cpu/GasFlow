"""
Driver Mobile Auth — App do Entregador (Fase 1)

Estende a Driver API v1 (Fase 14) com o contrato mobile do roadmap:

    POST /auth/mobile/login    — access_token (15 min, mini-JWT HS256 escopo
                                 "mobile") + refresh_token (7 dias, DB-backed
                                 com rotação e detecção de replay)
    POST /auth/mobile/refresh  — rotação: token reusado → família revogada
    POST /auth/mobile/logout   — revoga refresh + sessões do motorista
    GET  /driver/sync?since=   — delta sync por offline_sync_log

Sem dependência nova: o access token é um JWT HS256 enxuto (header.payload
b64url + HMAC via hashlib/hmac) — o PyInstaller não ganha pacote extra.
Refresh token é opaco e vive no banco (revogação imediata, auditoria).

Regras de segurança do prompt (seção 7): escopo "mobile" no token; rate
limit 10 login/min/IP; reuse de refresh revoga a família; toda query de
rota filtra por driver_id do token.
"""

import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.application.security.jwt_crypto import (
    TokenError,
    b64url,
    b64url_decode,
    decode,
    encode_with_now,
    ensure_file_secret,
    resolve_jwt_secret,
)
from app.domain.security.models import RateLimiter
from app.core.config import settings
from app.infrastructure.database.dependencies import get_db
from app.infrastructure.repositories.delivery_persistence_repository import (
    SQLAlchemyDriverRefreshTokenRepository,
    SQLAlchemyOfflineSyncLogRepository,
)
from sqlalchemy.orm import Session

router = APIRouter(tags=["driver-mobile"])

# ── Rate limiting (10 login/min/IP — prompt 3.1) ─────────────
_login_limiter = RateLimiter()


# ── Mini-JWT HS256 (stdlib) ──────────────────────────────────


# Os primitivos (base64url, assinatura, verificação e segredo) vivem em
# `app/application/security/jwt_crypto.py` e são compartilhados com o token do
# operador — uma implementação só de verificação de assinatura no app.


def _b64url(data: bytes) -> str:
    return b64url(data)


def _b64url_decode(data: str) -> bytes:
    return b64url_decode(data)


def _ensure_file_secret(path: str) -> str:
    """Secret estável gerado uma única vez e persistido FORA do repositório.

    Escrita atômica (tmp + replace) para não expor um secret parcialmente
    gravado em caso de crash. Usado como último recurso de configuração em
    desktop/instalação single-machine (o backend empacotado roda no PC do
    depósito, sem orquestração — um arquivo local é aceitável).
    """
    return ensure_file_secret(path)


def _jwt_secret() -> str:
    """Secret HS256 — dedicado do mobile (nunca reusa senha/sessão web).

    Ordem de resolução (auditoria de segurança — sem default hardcode em
    produção):
      1. env MOBILE_JWT_SECRET (≥32 bytes em produção)
      2. settings.mobile_jwt_secret (mesma origem, via config)
      3. arquivo gerado 1x em MOBILE_JWT_SECRET_FILE
         (default: <tempdir>/gasflow/mobile_jwt_secret.key)
      4. fallback "gasflow-dev-secret" APENAS fora de produção (testes/dev)
    """
    # Segredo DEDICADO do mobile — nunca reusa a chave do operador.
    return resolve_jwt_secret(
        env_var="MOBILE_JWT_SECRET",
        file_env_var="MOBILE_JWT_SECRET_FILE",
        settings_values=(settings.mobile_jwt_secret,),
        default_file_name="mobile_jwt_secret.key",
        environment=settings.environment,
    )


def issue_access_token(driver_id: str, tenant_id: str, expires_minutes: int = 15) -> str:
    """JWT HS256 mínimo com escopo "mobile" — verificado por hmac constante."""
    return encode_with_now(
        {
            "sub": driver_id,
            "tenant_id": tenant_id,
            "scope": "mobile",
            "role": "DRIVER",
            "jti": str(uuid.uuid4()),
        },
        _jwt_secret(),
        expires_seconds=expires_minutes * 60,
    )


def verify_access_token(token: str) -> Dict[str, Any]:
    """Verifica header, assinatura, exp (com leeway) e escopo.

    Regras da auditoria de segurança:
    - header "alg" diferente de HS256 → 401 ("alg: none"/confusão de
      algoritmo é rejeitado EXPLICITAMENTE, nunca tratado como unsigned)
    - assinatura comparada via hmac.compare_digest (timing-safe)
    - claim exp é OBRIGATÓRIO numérico — token sem exp nunca é aceito
    """
    try:
        return decode(token, _jwt_secret(), expected_scope="mobile")
    except TokenError as exc:
        # `exc.message` preserva exatamente os detalhes anteriores
        # ("Invalid token" / "Token expired" / "Invalid token scope").
        raise HTTPException(401, detail=exc.message) from exc


def _credentials_bearer(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, detail="Authentication required")
    return authorization[7:]


def get_mobile_context(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Dependência de auth para rotas mobile (escopo mobile obrigatório)."""
    token = _credentials_bearer(authorization)
    payload = verify_access_token(token)
    return {
        "driver_id": payload["sub"],
        "tenant_id": payload.get("tenant_id", "default"),
        "scope": payload.get("scope"),
        "token": token,
    }


# ── Schemas ──────────────────────────────────────────────────


class MobileLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)
    device_id: Optional[str] = Field(default=None, max_length=100)


class MobileTokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15 min em segundos
    driver_id: str
    tenant_id: str
    driver_name: str = ""


class MobileRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=200)


# ── Helpers de driver ────────────────────────────────────────


def _find_driver(db: Session, username: str):
    from app.infrastructure.repositories.delivery_model import DeliveryDriverModel

    return (
        db.query(DeliveryDriverModel)
        .filter(DeliveryDriverModel.username == username, DeliveryDriverModel.ativo == True)  # noqa: E712
        .first()
    )


def _driver_public_dict(driver) -> Dict[str, Any]:
    return {
        "driver_id": driver.codigo,
        "name": driver.nome,
        "phone": driver.telefone,
        "vehicle_plate": driver.placa or "",
        "tenant_id": driver.tenant_id or "default",
    }


def _issue_refresh(db: Session, driver_id: str, tenant_id: str) -> str:
    repo = SQLAlchemyDriverRefreshTokenRepository(db)
    token = secrets.token_urlsafe(48)
    repo.create_family(
        token=token,
        driver_id=driver_id,
        tenant_id=tenant_id,
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    return token


# ── Work hours (LGPD — prompt seção 8) ───────────────────────
# Configuração por tenant no quadro de configurações:
#   driver.work_hours.start / driver.work_hours.end ("HH:MM")


def _work_hours(db: Session, tenant_id: str) -> tuple:
    from app.application.settings.settings_service import SettingsService

    start = str(SettingsService(db).get_value("driver.work_hours.start", "06:00"))
    end = str(SettingsService(db).get_value("driver.work_hours.end", "22:00"))
    return start, end


def is_within_work_hours(db: Session, tenant_id: str, now: Optional[datetime] = None) -> bool:
    """Janela de trabalho (suporta travessia de meia-noite, ex. 18:00→02:00)."""
    now = now or datetime.utcnow()
    start_s, end_s = _work_hours(db, tenant_id)
    try:
        start_h, start_m = (int(p) for p in start_s.split(":")[:2])
        end_h, end_m = (int(p) for p in end_s.split(":")[:2])
    except ValueError:
        return True  # config inválida → não bloqueia (fail-open p/ operação)
    minutes = now.hour * 60 + now.minute
    start = start_h * 60 + start_m
    end = end_h * 60 + end_m
    if start <= end:
        return start <= minutes < end
    return minutes >= start or minutes < end  # janela cruza meia-noite


# ── Endpoints /auth/mobile/* ─────────────────────────────────


@router.post("/auth/mobile/login", response_model=MobileTokenPair)
def mobile_login(body: MobileLoginRequest, request: Request, db: Session = Depends(get_db)):
    """Login mobile: JWT 15min + refresh 7d. Rate limit 10/min/IP."""
    client_ip = request.client.host if request.client else "unknown"
    if not _login_limiter.check(f"mobile-login:{client_ip}", 10, 60):
        raise HTTPException(429, detail="Too many login attempts")

    driver = _find_driver(db, body.username)
    if driver is None:
        raise HTTPException(401, detail="Invalid credentials")
    if driver.password_hash:
        import bcrypt

        if not bcrypt.checkpw(body.password.encode(), driver.password_hash.encode()):
            raise HTTPException(401, detail="Invalid credentials")

    driver_id = driver.codigo
    tenant_id = driver.tenant_id or "default"
    access = issue_access_token(driver_id, tenant_id)
    refresh = _issue_refresh(db, driver_id, tenant_id)

    public = _driver_public_dict(driver)
    return MobileTokenPair(
        access_token=access,
        refresh_token=refresh,
        driver_id=driver_id,
        tenant_id=tenant_id,
        driver_name=public["name"],
    )


@router.post("/auth/mobile/refresh", response_model=MobileTokenPair)
def mobile_refresh(body: MobileRefreshRequest, db: Session = Depends(get_db)):
    """Rotação de refresh. Reuso de token rotacionado/revogado → família morta."""
    repo = SQLAlchemyDriverRefreshTokenRepository(db)
    record = repo.get_any(body.refresh_token)
    if not record or record.expires_at < datetime.utcnow():
        raise HTTPException(401, detail="Invalid refresh token")
    if record.status != "ACTIVE":
        # Replay detectado: revoga a família inteira (prompt seção 7).
        repo.revoke_family(str(record.family_id))
        raise HTTPException(401, detail="Refresh token reuse detected — session revoked")

    driver_id = str(record.driver_id)
    tenant_id = str(record.tenant_id)
    access = issue_access_token(driver_id, tenant_id)
    new_refresh = secrets.token_urlsafe(48)
    current_expiry = cast(datetime, record.expires_at)
    rotated = repo.rotate(
        record,
        new_refresh,
        new_expires_at=min(
            current_expiry,  # família não estende além do original de 7 dias
            datetime.utcnow() + timedelta(days=7),
        ),
    )

    driver_name = ""
    from app.infrastructure.repositories.delivery_model import DeliveryDriverModel

    driver = db.query(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == driver_id).first()
    if driver:
        driver_name = str(driver.nome)
    return MobileTokenPair(
        access_token=access,
        refresh_token=new_refresh,
        driver_id=str(rotated.driver_id),
        tenant_id=str(rotated.tenant_id),
        driver_name=driver_name,
    )


@router.post("/auth/mobile/logout")
def mobile_logout(
    body: MobileRefreshRequest,
    ctx: Dict[str, Any] = Depends(get_mobile_context),
    db: Session = Depends(get_db),
):
    """Revoga o refresh token informado + sessões legadas do motorista."""
    repo = SQLAlchemyDriverRefreshTokenRepository(db)
    record = repo.get_any(body.refresh_token)
    if record and record.driver_id == ctx["driver_id"]:
        repo.revoke_family(str(record.family_id))
    from app.infrastructure.repositories.delivery_persistence_repository import (
        SQLAlchemyDriverSessionRepository,
    )

    SQLAlchemyDriverSessionRepository(db).revoke_all_for_driver(ctx["driver_id"])
    return {"success": True}


# ── Delta sync (GET /driver/sync?since=) ─────────────────────


@router.get("/driver/sync")
def mobile_delta_sync(
    since: Optional[str] = Query(default=None),
    ctx: Dict[str, Any] = Depends(get_mobile_context),
    db: Session = Depends(get_db),
):
    """Delta de mudanças desde o timestamp ISO informado.

    Complementa o POST /driver/sync batch da Fase 14: o mobile traz o
    servidor de volta ao estado atual após ficar offline. Retorna mudanças
    do tenant + server_time; entregas do próprio motorista vêm completas,
    as demais como ids (o mobile filtra).
    """
    from app.infrastructure.repositories.delivery_persistence_repository import (
        SQLAlchemyDeliveryPersistenceRepository,
    )

    since_dt: Optional[datetime] = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            raise HTTPException(422, detail="since deve ser ISO 8601") from None

    sync_repo = SQLAlchemyOfflineSyncLogRepository(db)
    changes = sync_repo.changes_since(ctx["tenant_id"], since_dt) if since_dt else []

    delivery_repo = SQLAlchemyDeliveryPersistenceRepository(db, ctx["tenant_id"])
    deliveries_out: List[Dict[str, Any]] = []
    for change in changes:
        if change.entity_type != "delivery":
            continue
        record = delivery_repo.get_delivery(str(change.entity_id))
        if record and getattr(record, "driver_id", None) == ctx["driver_id"]:
            deliveries_out.append(
                {
                    "delivery_id": record.id,
                    "status": record.status,
                    "version": record.version,
                    "updated_at": record.updated_at.isoformat() if record.updated_at else None,
                }
            )

    return {
        "deliveries": deliveries_out,
        "route_changes": [
            {
                "entity_id": c.entity_id,
                "entity_type": c.entity_type,
                "action": c.action,
                "changed_at": c.changed_at.isoformat(),
            }
            for c in changes
            if c.entity_type != "delivery"
        ],
        "server_time": datetime.utcnow().isoformat(),
    }
