"""
Referral Service — F4 (Cupons + Indicação)

Fluxo (spec §3.5/§5, decisões G1/G2/G3):
1. Admin gera um invite_token para o cupom do cliente indicador.
2. Indicado se auto-cadastra via IA (tool register_referral) ou endpoint
   público com o token.
3. Ambos (indicador + indicado) ganham cupom de MESMO valor (G1),
   validade de 90 dias (G3), salvo no perfil de cada um.
4. Limite de 10 indicações/mês por cliente (G2) — a 11ª é bloqueada.

Não altera a regra "1 cupom por pedido": cupom de indicação é um cupom
comum do módulo existente (validação/aplicação ficam no CouponService).
"""

import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DBSession

from app.core.logging import setup_logging
from app.infrastructure.repositories.coupon_model import (
    CouponModel,
    CouponRedemptionModel,
    ReferralModel,
)

logger = setup_logging("INFO")

# Defaults das decisões travadas (configuráveis via SettingsService)
DEFAULT_MAX_REFERRALS_PER_MONTH = 10
DEFAULT_COUPON_VALIDITY_DAYS = 90

TOKEN_PREFIX = "GF-INV-"
TOKEN_LENGTH = 24  # secrets.token_urlsafe(24) → string URL-safe


class ReferralError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _to_d(value) -> Any:
    from decimal import Decimal

    return Decimal(str(value or 0))


class ReferralService:
    def __init__(self, db: DBSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    # ── Config (settings com fallback nos defaults) ───────

    @staticmethod
    def _setting(key: str, default: int) -> int:
        try:
            from sqlalchemy.orm import Session as _Session

            from app.application.settings.settings_service import SettingsService
            from app.infrastructure.database.init_db import engine

            session = _Session(bind=engine)
            try:
                value = SettingsService(session).get_value(key, default)
            finally:
                session.close()
            return int(value)
        except Exception:
            return default

    def max_per_month(self) -> int:
        return self._setting("referral.max_per_month", DEFAULT_MAX_REFERRALS_PER_MONTH)

    def validity_days(self) -> int:
        return self._setting("referral.coupon_validity_days", DEFAULT_COUPON_VALIDITY_DAYS)

    # ── Token de convite ──────────────────────────────────

    def generate_invite(self, referrer_client_codigo: str) -> ReferralModel:
        """Cria a indicação pendente + cupom do indicador, retorna o registro.

        O cupom do indicador é gerado no ato do convite (ele já tem "direito
        adquirido"); o do indicado nasce no auto-cadastro (mesmo valor).
        """
        # Limite mensal inclui convites pendentes (não só completados)
        self._check_monthly_limit(referrer_client_codigo)

        # Valor de referência: último cupom ativo ou default fixo (R$10)
        value, coupon_type = self._reference_offer()

        token = f"{TOKEN_PREFIX}{secrets.token_urlsafe(TOKEN_LENGTH)}"
        referrer_coupon = self._create_referral_coupon(
            code=f"INDICA-{token[len(TOKEN_PREFIX):len(TOKEN_PREFIX)+12].upper()}",
            value=value,
            coupon_type=coupon_type,
            owner_codigo=referrer_client_codigo,
        )

        referral = ReferralModel(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            invite_token=token,
            referrer_client_codigo=referrer_client_codigo,
            referrer_coupon_id=referrer_coupon.id,
        )
        self.db.add(referral)
        self.db.commit()
        self.db.refresh(referral)
        logger.info(
            "referral.invite_created",
            extra={"referral_id": referral.id, "referrer": referrer_client_codigo},
        )
        return referral

    def get_by_token(self, token: str) -> Optional[ReferralModel]:
        if not token or not token.startswith(TOKEN_PREFIX):
            return None
        return (
            self.db.query(ReferralModel)
            .filter(
                ReferralModel.invite_token == token,
                ReferralModel.tenant_id == self.tenant_id,
            )
            .first()
        )

    # ── Auto-cadastro (completa a indicação) ──────────────

    def complete_signup(
        self,
        invite_token: str,
        name: str,
        phone: str,
        address: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Registra o indicado e gera os cupons de ambos (idempotente por token).

        Retorna dict com referred/referrer, cliente criado e cupons gerados.
        """
        referral = self.get_by_token(invite_token)
        if not referral:
            raise ReferralError("TOKEN_NOT_FOUND", "Token de convite inválido ou expirado.", 404)

        if referral.referred_client_codigo:
            # Idempotente: token já usado → retorna o estado atual
            referred = self._client_by_codigo(referral.referred_client_codigo)
            return {
                "idempotent_replay": True,
                "referral": referral,
                "referred_client": referred,
                "referrer_client": self._client_by_codigo(referral.referrer_client_codigo),
                "coupons": self._referral_coupons(referral),
            }

        # Cria/atualiza o cliente indicado (upsert idempotente por telefone)
        client = self._upsert_referred(name, phone, address or {})

        # Cupom do indicado — mesmo valor do do indicador (G1)
        value, coupon_type = self._reference_offer()
        referred_coupon = self._create_referral_coupon(
            code=f"BEMVINDO-{client.codigo}-{uuid.uuid4().hex[:6].upper()}",
            value=value,
            coupon_type=coupon_type,
            owner_codigo=client.codigo,
        )

        referral.referred_client_codigo = client.codigo
        referral.referred_coupon_id = referred_coupon.id
        referral.referred_name = name
        referral.referred_phone = phone
        self.db.commit()
        self.db.refresh(referral)

        logger.info(
            "referral.signup_completed",
            extra={"referral_id": referral.id, "referred": client.codigo},
        )
        return {
            "idempotent_replay": False,
            "referral": referral,
            "referred_client": client,
            "referrer_client": self._client_by_codigo(referral.referrer_client_codigo),
            "coupons": self._referral_coupons(referral),
        }

    # ── Consultas para perfil/IA ──────────────────────────

    def client_coupons(self, client_codigo: str) -> Dict[str, List[Dict[str, Any]]]:
        """Cupons do cliente separados por status (ativos/usados/expirados)."""
        now = datetime.utcnow()
        coupons = self.db.query(CouponModel).filter(CouponModel.tenant_id == self.tenant_id).all()
        mine = [c for c in coupons if client_codigo in [str(x) for x in (c.applicable_customers or [])]]
        # Redemptions deste cliente (cupons já usados em pedidos)
        used_coupon_ids = {
            r.coupon_id
            for r in self.db.query(CouponRedemptionModel)
            .filter(
                CouponRedemptionModel.client_codigo == client_codigo,
                CouponRedemptionModel.tenant_id == self.tenant_id,
            )
            .all()
        }

        active, used, expired = [], [], []
        for c in mine:
            item = {
                "id": c.id,
                "code": c.code,
                "type": c.type,
                "value": float(c.value) if c.value is not None else None,
                "end_date": c.end_date.isoformat() if c.end_date else None,
                "is_referral": bool(c.is_referral),
            }
            if c.id in used_coupon_ids:
                used.append(item)
            elif c.end_date and c.end_date < now:
                expired.append(item)
            elif c.is_active:
                active.append(item)
            else:
                expired.append(item)
        return {"active": active, "used": used, "expired": expired}

    def client_referrals(self, client_codigo: str) -> Dict[str, Any]:
        """Histórico de indicações do cliente (como indicador)."""
        rows = (
            self.db.query(ReferralModel)
            .filter(
                ReferralModel.referrer_client_codigo == client_codigo,
                ReferralModel.tenant_id == self.tenant_id,
            )
            .order_by(ReferralModel.created_at.desc())
            .all()
        )
        return {
            "total": len(rows),
            "completed": sum(1 for r in rows if r.referred_client_codigo),
            "pending": sum(1 for r in rows if not r.referred_client_codigo),
            "items": [
                {
                    "id": r.id,
                    "invite_token": r.invite_token,
                    "referred_name": r.referred_name,
                    "referred_client_codigo": r.referred_client_codigo,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "completed": bool(r.referred_client_codigo),
                }
                for r in rows
            ],
            "monthly_limit": self.max_per_month(),
        }

    # ── Internos ──────────────────────────────────────────

    def _check_monthly_limit(self, referrer_client_codigo: str) -> None:
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        count = (
            self.db.query(ReferralModel)
            .filter(
                ReferralModel.referrer_client_codigo == referrer_client_codigo,
                ReferralModel.tenant_id == self.tenant_id,
                ReferralModel.created_at >= month_start,
            )
            .count()
        )
        limit = self.max_per_month()
        if count >= limit:
            raise ReferralError(
                "MONTHLY_LIMIT_REACHED",
                f"Limite de {limit} indicações por mês atingido.",
                429,
            )

    def _reference_offer(self):
        """Tipo/valor do cupom de indicação: herda do último cupom de referral
        criado no tenant ou usa default (FIXED R$10)."""
        last = (
            self.db.query(CouponModel)
            .filter(
                CouponModel.tenant_id == self.tenant_id,
                CouponModel.is_referral.is_(True),
            )
            .order_by(CouponModel.created_at.desc())
            .first()
        )
        if last and last.value:
            return _to_d(last.value), last.type
        return _to_d(10), "FIXED"

    def _create_referral_coupon(self, code: str, value, coupon_type: str, owner_codigo: str) -> CouponModel:
        days = self.validity_days()
        now = datetime.utcnow()
        coupon = CouponModel(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            code=code.strip().upper(),
            name="Cupom de indicação",
            description="Gerado automaticamente pelo programa de indicação.",
            type=coupon_type,
            value=value,
            min_order_value=_to_d(0),
            applicable_products=[],
            applicable_customers=[owner_codigo],
            start_date=now,
            end_date=now + timedelta(days=days),
            usage_limit=1,
            usage_per_customer=1,
            usage_count=0,
            is_active=True,
            created_by="referral_system",
            is_referral=True,
        )
        self.db.add(coupon)
        self.db.commit()
        self.db.refresh(coupon)
        return coupon

    def _upsert_referred(self, name: str, phone: str, address: Dict[str, str]):
        from app.application.contacts.service import ContactService, normalize_phone
        from app.infrastructure.repositories.client_repository import (
            SQLAlchemyClientRepository,
        )

        digits = normalize_phone(phone)
        if len(digits) < 8:
            raise ReferralError("PHONE_INVALID", "Telefone inválido para cadastro.")

        repo = SQLAlchemyClientRepository(self.db)
        svc = ContactService(repo)
        client, _action = svc.upsert_contact(
            {
                "telefone": digits,
                "nome": name or "",
                "rua": address.get("rua") or "",
                "numero": address.get("numero") or "",
                "bairro": address.get("bairro") or "",
            }
        )
        return client

    def _client_by_codigo(self, codigo: Optional[str]):
        if not codigo:
            return None
        from app.infrastructure.repositories.client_repository import (
            SQLAlchemyClientRepository,
        )

        return SQLAlchemyClientRepository(self.db).buscar_por_codigo(codigo)

    def _referral_coupons(self, referral: ReferralModel) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key, coupon_id in (
            ("referrer", referral.referrer_coupon_id),
            ("referred", referral.referred_coupon_id),
        ):
            if not coupon_id:
                out[key] = None
                continue
            c = self.db.query(CouponModel).filter(CouponModel.id == coupon_id).first()
            out[key] = (
                {
                    "id": c.id,
                    "code": c.code,
                    "type": c.type,
                    "value": float(c.value) if c.value is not None else None,
                    "end_date": c.end_date.isoformat() if c.end_date else None,
                }
                if c
                else None
            )
        return out
