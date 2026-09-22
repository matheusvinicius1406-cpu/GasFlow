"""
ReferralService Tests — F4.5 (Cupons + Indicação)

Cobre: criação de indicação (2 cupons, mesmo valor), validade 90 dias,
limite 10/mês, validação de token (prefixo GF-INV-), cupons agrupados
por status, histórico de indicações.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from app.infrastructure.database.connection import SessionLocal
from app.infrastructure.repositories.coupon_model import (
    CouponModel,
    ReferralModel,
)
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.domain.client.entity import Client
from app.application.coupon.referral_service import (
    ReferralService,
    ReferralError,
    TOKEN_PREFIX,
)


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()


def _create_client(db, codigo, nome="Test Client", telefone="11999990000"):
    """Cria um cliente de teste diretamente no banco."""
    repo = SQLAlchemyClientRepository(db)
    existing = repo.buscar_por_codigo(codigo)
    if existing:
        return existing
    client = Client(
        codigo=codigo,
        nome=nome,
        telefone=telefone,
        rua="Rua Teste",
        numero="100",
        bairro="Centro",
    )
    return repo.criar(client)


class TestReferralService:
    def test_create_referral_creates_two_coupons_same_value(self, db):
        """G1: indicador e indicado recebem cupom de mesmo valor."""
        referrer = _create_client(db, "000001", "Indicador", "11999990001")
        referred = _create_client(db, "000002", "Indicado", "11999990002")

        svc = ReferralService(db, "default")

        # Gera convite (cria cupom do indicador)
        referral = svc.generate_invite(referrer.codigo)
        assert referral.invite_token.startswith(TOKEN_PREFIX)
        assert referral.referrer_coupon_id is not None

        # Cupom do indicador
        referrer_coupon = db.query(CouponModel).filter(CouponModel.id == referral.referrer_coupon_id).first()
        assert referrer_coupon is not None
        assert referrer_coupon.is_referral is True
        assert referrer_coupon.applicable_customers == [referrer.codigo]

        # Completa o signup (cria cupom do indicado)
        result = svc.complete_signup(
            referral.invite_token,
            referred.nome,
            referred.telefone,
        )
        assert result["referral"].id == referral.id

        referred_coupon = db.query(CouponModel).filter(CouponModel.id == referral.referred_coupon_id).first()
        assert referred_coupon is not None
        assert referred_coupon.is_referral is True

        # G1: mesmo valor
        assert referrer_coupon.value == referred_coupon.value
        assert referrer_coupon.type == referred_coupon.type

    def test_referral_coupon_validity_90_days(self, db):
        """G3: validade de 90 dias (±1 dia)."""
        referrer = _create_client(db, "000090", "Validador", "11999990090")
        svc = ReferralService(db, "default")

        referral = svc.generate_invite(referrer.codigo)
        coupon = db.query(CouponModel).filter(CouponModel.id == referral.referrer_coupon_id).first()

        now = datetime.utcnow()
        expected_end = now + timedelta(days=90)
        diff = abs((coupon.end_date - expected_end).total_seconds())
        assert diff < 86400  # ±1 dia

    def test_11th_referral_blocked(self, db):
        """11ª indicação no mês deve ser bloqueada."""
        referrer = _create_client(db, "000011", "Blocked", "11999990011")
        svc = ReferralService(db, "default")

        # Cria 10 referrals no mês corrente
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        for i in range(10):
            referred = _create_client(db, f"11{i:04d}", f"Referred {i}", f"1199999{1000 + i}")
            referral = ReferralModel(
                id=f"test-ref-11-{i:02d}",
                tenant_id="default",
                invite_token=f"{TOKEN_PREFIX}test-token-11-{i}",
                referrer_client_codigo=referrer.codigo,
                created_at=month_start + timedelta(hours=i),
            )
            db.add(referral)
        db.commit()

        # 11ª deve falhar
        with pytest.raises(ReferralError) as exc:
            svc.generate_invite(referrer.codigo)
        assert exc.value.code == "MONTHLY_LIMIT_REACHED"

    def test_10th_referral_allowed(self, db):
        """10ª indicação no mês deve ser permitida."""
        referrer = _create_client(db, "000010", "Allowed", "11999990010")
        svc = ReferralService(db, "default")

        # Cria 9 referrals no mês corrente
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        for i in range(9):
            referred = _create_client(db, f"10{i:04d}", f"Referred {i}", f"1199999{2000 + i}")
            referral = ReferralModel(
                id=f"test-ref-10-{i:02d}",
                tenant_id="default",
                invite_token=f"{TOKEN_PREFIX}test-token-10-{i}",
                referrer_client_codigo=referrer.codigo,
                created_at=month_start + timedelta(hours=i),
            )
            db.add(referral)
        db.commit()

        # 10ª deve passar
        referral = svc.generate_invite(referrer.codigo)
        assert referral.id is not None
        assert referral.invite_token.startswith(TOKEN_PREFIX)

    def test_validate_invite_token_accepts_gf_inv_prefix(self, db):
        """Token com prefixo GF-INV- é aceito."""
        referrer = _create_client(db, "000020", "Prefixo", "11999990020")
        svc = ReferralService(db, "default")

        referral = svc.generate_invite(referrer.codigo)
        assert referral.invite_token.startswith(TOKEN_PREFIX)

        found = svc.get_by_token(referral.invite_token)
        assert found is not None
        assert found.id == referral.id

    def test_validate_invite_token_rejects_non_gf_inv(self, db):
        """Token sem prefixo GF-INV- retorna None."""
        svc = ReferralService(db, "default")
        found = svc.get_by_token("invalid-token-12345")
        assert found is None

    def test_validate_invite_token_rejects_empty(self, db):
        """Token vazio retorna None."""
        svc = ReferralService(db, "default")
        found = svc.get_by_token("")
        assert found is None

    def test_invite_token_single_use(self, db):
        """Token de convite é single-use: 2º uso retorna erro."""
        referrer = _create_client(db, "000050", "SingleUse", "11999990050")
        referred = _create_client(db, "000051", "ReferredOnce", "11999990051")
        svc = ReferralService(db, "default")

        referral = svc.generate_invite(referrer.codigo)
        token = referral.invite_token

        # 1º uso — sucesso
        result = svc.complete_signup(token, referred.nome, referred.telefone)
        assert result["referral"].id == referral.id

        # 2º uso — erro
        with pytest.raises(ReferralError) as exc:
            svc.complete_signup(token, "Outro", "11999990052")
        assert exc.value.code == "INVITE_ALREADY_USED"

    def test_client_coupons_returns_grouped_by_status(self, db):
        """client_coupons retorna cupons agrupados por status."""
        client = _create_client(db, "000030", "Grouped", "11999990030")
        svc = ReferralService(db, "default")

        now = datetime.utcnow()

        # Cria cupom ativo
        active = CouponModel(
            id="test-active-1",
            tenant_id="default",
            code="ACTIVE1",
            type="FIXED",
            value=Decimal("10"),
            min_order_value=Decimal("0"),
            applicable_customers=[client.codigo],
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=30),
            usage_limit=1,
            usage_per_customer=1,
            is_active=True,
        )
        # Cupaom expirado
        expired = CouponModel(
            id="test-expired-1",
            tenant_id="default",
            code="EXPIRED1",
            type="FIXED",
            value=Decimal("5"),
            min_order_value=Decimal("0"),
            applicable_customers=[client.codigo],
            start_date=now - timedelta(days=60),
            end_date=now - timedelta(days=1),
            usage_limit=1,
            usage_per_customer=1,
            is_active=True,
        )
        db.add_all([active, expired])
        db.commit()

        result = svc.client_coupons(client.codigo)
        assert "active" in result
        assert "used" in result
        assert "expired" in result

        active_codes = [c["code"] for c in result["active"]]
        expired_codes = [c["code"] for c in result["expired"]]
        assert "ACTIVE1" in active_codes
        assert "EXPIRED1" in expired_codes

    def test_client_referrals_returns_history(self, db):
        """client_referrals retorna histórico completo."""
        referrer = _create_client(db, "000040", "Historico", "11999990040")
        svc = ReferralService(db, "default")

        # Cria 2 referrals como indicador
        for i in range(2):
            referral = ReferralModel(
                id=f"test-hist-{i}",
                tenant_id="default",
                invite_token=f"{TOKEN_PREFIX}hist-token-{i}",
                referrer_client_codigo=referrer.codigo,
                referred_client_codigo=f"R{i}" if i == 0 else None,
                referred_name=f"Pessoa {i}" if i == 0 else None,
                created_at=datetime.utcnow() - timedelta(days=i),
            )
            db.add(referral)
        db.commit()

        result = svc.client_referrals(referrer.codigo)
        assert result["total"] == 2
        assert result["completed"] == 1  # só o primeiro tem referred_client_codigo
        assert result["pending"] == 1
        assert result["monthly_limit"] == 10

    def test_coupon_code_length_is_12_chars(self, db):
        """F4.5 bugfix: código do cupom de indicação usa 12 chars (não 8)."""
        referrer = _create_client(db, "000060", "CodeLen", "11999990060")
        svc = ReferralService(db, "default")

        referral = svc.generate_invite(referrer.codigo)
        coupon = db.query(CouponModel).filter(CouponModel.id == referral.referrer_coupon_id).first()

        # Código deve ter pelo menos 12 chars após o prefixo "INDICA-"
        code_part = coupon.code.replace("INDICA-", "")
        assert len(code_part) >= 12, f"Código muito curto: {coupon.code}"

    def test_coupon_code_uniqueness_200(self, db):
        """F4.5 bugfix: 200 cupons gerados devem ter códigos únicos."""
        codes = set()
        for i in range(200):
            referrer = _create_client(db, f"61{i:04d}", f"Unique-{i}", f"1199999{6100 + i}")
            svc = ReferralService(db, "default")
            referral = svc.generate_invite(referrer.codigo)
            coupon = db.query(CouponModel).filter(CouponModel.id == referral.referrer_coupon_id).first()
            codes.add(coupon.code)

        assert len(codes) == 200, f"Colisão detectada: {200 - len(codes)} códigos duplicados"

    def test_bemvindo_coupon_code_has_unique_suffix(self, db):
        """F4.5 bugfix: BEMVINDO-{codigo} tem sufixo UUID único."""
        referrer = _create_client(db, "000062", "BemVindo", "11999990062")
        svc = ReferralService(db, "default")

        codes = []
        for i in range(5):
            token = svc.generate_invite(referrer.codigo).invite_token
            referred = _create_client(db, f"62{i:04d}", f"BV-{i}", f"1199999{6300 + i}")
            svc.complete_signup(token, referred.nome, referred.telefone)

        # Pega todos os cupons BEMVINDO
        coupons = (
            db.query(CouponModel)
            .filter(
                CouponModel.tenant_id == "default",
                CouponModel.code.like("BEMVINDO-%"),
            )
            .all()
        )
        codes = [c.code for c in coupons]

        # Todos os códigos BEMVINDO devem ser únicos
        assert len(codes) == len(set(codes)), f"Colisão BEMVINDO: {codes}"
