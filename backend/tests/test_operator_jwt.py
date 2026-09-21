"""Tokens do operador (B5) — access JWT curto + refresh rotativo.

O que estes testes protegem, em ordem de gravidade:

1. **Revogação manda**: o access é JWT, mas não é stateless — `logout` tem que
   matar o acesso na hora. Se isso quebrar, sair do console não desconecta.
2. **Escopo não vaza**: token do app do entregador (escopo `mobile`) nunca é
   aceito no console, e vice-versa; segredo é dedicado por escopo.
3. **Reuso de refresh** revoga a família inteira (sinal de token vazado).
4. **Compatibilidade**: o token opaco emitido antes do B5 continua valendo.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

from app.application.security import jwt_crypto, operator_token
from app.application.security.auth_service import AuthService
from app.domain.security.models import SystemRole
from app.infrastructure.database.base import Base
from app.infrastructure.repositories.auth_repository import SQLAlchemySessionRepository

ADMIN = ("admin", "test_password_123")


@pytest.fixture
def db():
    """Engine SQLite em memória nova por teste (mesmo padrão do repo)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = DBSession(bind=engine)
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def auth_service(db):
    return AuthService(db=db)


def _login(auth_service, username=ADMIN[0], password=ADMIN[1], platform="desktop"):
    result = auth_service.login(username, password, platform=platform)
    assert result["success"] is True, result
    return result


# ── 1. Emissão ───────────────────────────────────────────


class TestIssue:
    def test_login_emits_access_jwt_and_refresh(self, auth_service):
        result = _login(auth_service)

        access = result["access_token"]
        refresh = result["refresh_token"]
        assert operator_token.looks_like_jwt(access) is True
        # Refresh é opaco de propósito: nunca JWT (não carrega claim alguma).
        assert operator_token.looks_like_jwt(refresh) is False
        assert len(refresh) >= 40
        assert result["token_type"] == "Bearer"
        assert result["expires_in"] == operator_token.ACCESS_TTL_MINUTES * 60

    def test_refresh_hash_matches_stored_only(self, db, auth_service):
        result = _login(auth_service)
        repo = SQLAlchemySessionRepository(db)
        model, is_reuse = repo.find_by_refresh_hash(operator_token.hash_refresh_token(result["refresh_token"]))
        assert model is not None
        assert is_reuse is False
        # O token em claro não é o que está gravado.
        assert model.refresh_token_hash != result["refresh_token"]

    def test_platform_is_carried_in_token(self, auth_service):
        result = _login(auth_service, platform="mobile")
        payload = operator_token.verify_access_token(result["access_token"])
        assert payload["platform"] == "mobile"

    def test_unknown_platform_falls_back_to_desktop(self, auth_service):
        result = _login(auth_service, platform="navegador-espacial")
        payload = operator_token.verify_access_token(result["access_token"])
        assert payload["platform"] == operator_token.PLATFORM_DESKTOP


# ── 2. Validação ─────────────────────────────────────────


class TestValidate:
    def test_access_token_validates(self, auth_service):
        result = _login(auth_service)
        ctx = auth_service.validate_token(result["access_token"])
        assert ctx is not None
        assert ctx.user_id == "admin-001"
        assert ctx.tenant_id == "default"
        assert ctx.role == SystemRole.ADMIN

    def test_opaque_token_still_works(self, auth_service):
        """Compatibilidade: token opaco (pré-B5) segue válido."""
        result = _login(auth_service)
        ctx = auth_service.validate_token(result["token"])
        assert ctx is not None
        assert ctx.user_id == "admin-001"

    def test_garbage_is_rejected(self, auth_service):
        assert auth_service.validate_token("nao.e.umtoken") is None
        assert auth_service.validate_token("") is None

    def test_signature_of_other_secret_is_rejected(self, auth_service):
        forged = jwt_crypto.encode_with_now(
            {"sub": "admin-001", "tenant_id": "default", "scope": operator_token.OPERATOR_SCOPE},
            "outro-segredo-qualquer",
            expires_seconds=900,
        )
        assert auth_service.validate_token(forged) is None

    def test_mobile_scope_is_not_accepted(self, auth_service):
        """Token do entregador (escopo `mobile`) não entra no console."""
        from app.application.security.jwt_crypto import encode_with_now

        mobile_token = encode_with_now(
            {"sub": "driver-1", "tenant_id": "default", "scope": "mobile"},
            operator_token.operator_jwt_secret(),
            expires_seconds=900,
        )
        assert auth_service.validate_token(mobile_token) is None

    def test_expired_token_is_rejected(self, auth_service):
        expired = jwt_crypto.encode_with_now(
            {"sub": "admin-001", "tenant_id": "default", "sid": "s", "scope": operator_token.OPERATOR_SCOPE},
            operator_token.operator_jwt_secret(),
            expires_seconds=-3600,
        )
        assert auth_service.validate_token(expired) is None

    def test_jwt_of_missing_session_is_rejected(self, auth_service):
        orphan = operator_token.issue_access_token(
            user_id="admin-001",
            tenant_id="default",
            session_id="sessao-que-nao-existe",
            role="ADMIN",
        )
        assert auth_service.validate_token(orphan) is None


# ── 3. Revogação ─────────────────────────────────────────


class TestRevocation:
    def test_logout_kills_access_token(self, auth_service):
        result = _login(auth_service)
        access = result["access_token"]
        assert auth_service.validate_token(access) is not None

        assert auth_service.logout(access) is True
        assert auth_service.validate_token(access) is None

    def test_logout_accepts_opaque_token(self, auth_service):
        result = _login(auth_service)
        assert auth_service.logout(result["token"]) is True
        assert auth_service.validate_token(result["access_token"]) is None

    def test_logout_twice_returns_false(self, auth_service):
        result = _login(auth_service)
        assert auth_service.logout(result["access_token"]) is True
        assert auth_service.logout(result["access_token"]) is False


# ── 4. Refresh rotativo ──────────────────────────────────


class TestRefresh:
    def test_refresh_rotates_both_tokens(self, auth_service):
        first = _login(auth_service)
        second = auth_service.refresh_session(first["refresh_token"])

        assert second is not None
        assert second["refresh_token"] != first["refresh_token"]
        assert second["access_token"] != first["access_token"]
        assert second["expires_in"] == operator_token.ACCESS_TTL_MINUTES * 60
        assert auth_service.validate_token(second["access_token"]) is not None

    def test_stale_access_still_valid_until_revoked(self, auth_service):
        """O access antigo não é invalidado pela rotação (ele é curto de propósito)."""
        first = _login(auth_service)
        auth_service.refresh_session(first["refresh_token"])
        assert auth_service.validate_token(first["access_token"]) is not None

    def test_refresh_reuse_revokes_session(self, auth_service):
        first = _login(auth_service)
        second = auth_service.refresh_session(first["refresh_token"])
        assert second is not None

        # Reuso do refresh já rotacionado: nada é emitido...
        assert auth_service.refresh_session(first["refresh_token"]) is None
        # ...e a família inteira morre, inclusive o access recém-emitido.
        assert auth_service.validate_token(second["access_token"]) is None

    def test_unknown_refresh_is_rejected(self, auth_service):
        _login(auth_service)
        assert auth_service.refresh_session("refresh-que-nunca-existiu-aaaaaaaaaaaaaaaaaaaa") is None

    def test_refresh_after_logout_is_rejected(self, auth_service):
        result = _login(auth_service)
        auth_service.logout(result["access_token"])
        assert auth_service.refresh_session(result["refresh_token"]) is None

    def test_expired_refresh_is_rejected(self, db, auth_service):
        """Refresh vencido não renova, mesmo com sessão ativa."""
        result = _login(auth_service)
        model, _ = SQLAlchemySessionRepository(db).find_by_refresh_hash(
            operator_token.hash_refresh_token(result["refresh_token"])
        )
        model.refresh_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
        assert auth_service.refresh_session(result["refresh_token"]) is None

    def test_refresh_reissues_tenant_and_role(self, auth_service):
        result = _login(auth_service)
        refreshed = auth_service.refresh_session(result["refresh_token"])
        assert refreshed["tenant_id"] == "default"
        assert refreshed["role"] == SystemRole.ADMIN.value
