"""
AI Referral Tools Tests — F4.5 (Cupons + Indicação)

Cobre: register_referral (happy-path, campos obrigatórios, rate limit,
token inválido, idempotência) e list_client_coupons (happy-path, sem cupons,
campo obrigatório).
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from app.infrastructure.database.connection import SessionLocal
from app.infrastructure.repositories.coupon_model import (
    CouponModel,
)
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.domain.client.entity import Client
from app.application.coupon.referral_service import ReferralService
from app.application.ai.tools_impl import AIToolsFactory


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def factory(db):
    """Factory com sessão compartilhada para isolar rate limit."""
    return AIToolsFactory(db_session=db)


def _create_client(db, codigo, nome="Test Client", telefone="11999990000"):
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


def _create_invite_token(db, referrer_codigo):
    """Gera um invite token para um cliente."""
    svc = ReferralService(db, "default")
    referral = svc.generate_invite(referrer_codigo)
    return referral.invite_token


class TestRegisterReferral:
    def test_happy_path(self, factory, db):
        """Cadastro via token cria cliente + cupons para ambos."""
        referrer = _create_client(db, "000001", "Indicador AI", "11999993001")
        token = _create_invite_token(db, referrer.codigo)

        result = factory.register_referral(
            {
                "invite_token": token,
                "name": "Novo Indicado",
                "phone": "11999994002",
                "rua": "Rua Nova",
                "numero": "200",
                "bairro": "Centro",
            }
        )

        assert result.success is True
        assert result.data["referred_codigo"] is not None
        assert result.data["referrer_codigo"] == referrer.codigo
        assert result.data["referred_coupon"] is not None
        assert result.data["referrer_coupon"] is not None
        assert result.data["idempotent"] is False
        assert "R$" in result.display_message

    def test_missing_token(self, factory):
        """Sem token retorna erro."""
        result = factory.register_referral(
            {
                "name": "Teste",
                "phone": "11999991003",
            }
        )
        assert result.success is False
        assert "obrigatórios" in result.error

    def test_missing_name(self, factory, db):
        """Sem nome retorna erro."""
        referrer = _create_client(db, "000002", "Indicador 2", "11999993004")
        token = _create_invite_token(db, referrer.codigo)

        result = factory.register_referral(
            {
                "invite_token": token,
                "phone": "11999991005",
            }
        )
        assert result.success is False

    def test_missing_phone(self, factory, db):
        """Sem telefone retorna erro."""
        referrer = _create_client(db, "000003", "Indicador 3", "11999993006")
        token = _create_invite_token(db, referrer.codigo)

        result = factory.register_referral(
            {
                "invite_token": token,
                "name": "Sem Phone",
            }
        )
        assert result.success is False

    def test_invalid_token(self, factory):
        """Token inválido retorna erro."""
        result = factory.register_referral(
            {
                "invite_token": "INVALID-TOKEN-12345",
                "name": "Fantasma",
                "phone": "11999991007",
            }
        )
        assert result.success is False
        assert "inválido" in result.error.lower()

    def test_rate_limit_phone(self, factory, db):
        """3 tentativas por telefone/hora é bloqueado na 4ª."""
        referrer = _create_client(db, "000004", "Indicador 4", "11999993008")

        # 3 tentativas com MESMO telefone (rate limit é por telefone)
        for i in range(3):
            token = _create_invite_token(db, referrer.codigo)
            result = factory.register_referral(
                {
                    "invite_token": token,
                    "name": f"Pessoa {i}",
                    "phone": "11999993100",
                }
            )
            assert result.success is True, f"Tentativa {i + 1} deveria passar"

        # 4ª tentativa com mesmo telefone deve ser bloqueada
        token = _create_invite_token(db, referrer.codigo)
        result = factory.register_referral(
            {
                "invite_token": token,
                "name": "Bloqueado",
                "phone": "11999993100",
            }
        )
        assert result.success is False
        assert "Muitas tentativas" in result.error

    def test_token_single_use(self, factory, db):
        """Token de convite é single-use: 2º uso retorna erro."""
        referrer = _create_client(db, "000005", "Indicador 5", "11999993011")
        token = _create_invite_token(db, referrer.codigo)

        # Primeira chamada — sucesso
        result1 = factory.register_referral(
            {
                "invite_token": token,
                "name": "Único Uso",
                "phone": "11999994012",
            }
        )
        assert result1.success is True

        # Segunda chamada — erro INVITE_ALREADY_USED
        result2 = factory.register_referral(
            {
                "invite_token": token,
                "name": "Tentar de novo",
                "phone": "11999994013",
            }
        )
        assert result2.success is False
        assert "já foi utilizado" in result2.error


class TestListClientCoupons:
    def test_happy_path(self, factory, db):
        """Lista cupons de um cliente com cupons."""
        client = _create_client(db, "000010", "Com Cupons", "11999993020")
        now = datetime.utcnow()

        # Cria cupom ativo
        coupon = CouponModel(
            id="test-list-1",
            tenant_id="default",
            code="LIST01",
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
        db.add(coupon)
        db.commit()

        result = factory.list_client_coupons(
            {
                "customer_codigo": client.codigo,
            }
        )
        assert result.success is True
        assert result.data["count"] >= 1
        assert len(result.data["coupons"]) >= 1
        assert "cupom" in result.display_message.lower()

    def test_no_coupons(self, factory, db):
        """Cliente sem cupons retorna mensagem informativa."""
        client = _create_client(db, "000011", "Sem Cupons", "11999993021")

        result = factory.list_client_coupons(
            {
                "customer_codigo": client.codigo,
            }
        )
        assert result.success is True
        assert result.data["count"] == 0
        assert "Nenhum cupom" in result.display_message

    def test_missing_customer_codigo(self, factory):
        """Sem customer_codigo retorna erro."""
        result = factory.list_client_coupons({})
        assert result.success is False
        assert "obrigatório" in result.error
