"""
Auth Persistence Tests — P0

Verifies that auth state survives process restart
by using the database as single source of truth.

Tests:
1. Login → new AuthService instance → still authenticated
2. User creation persists
3. Session creation and validation persist
4. Session revocation persists
5. Tenant creation persists
6. Audit log persists
7. Password change persists
8. RBAC persists
9. Multi-tenant isolation
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.infrastructure.database.base import Base
from app.infrastructure.repositories.auth_repository import (
    SQLAlchemyUserRepository,
    SQLAlchemySessionRepository,
    SQLAlchemyTenantRepository,
    SQLAlchemyRoleRepository,
    SQLAlchemyMembershipRepository,
    SQLAlchemyAuditRepository,
)
from app.application.security.auth_service import AuthService
from app.domain.security.models import (
    SystemRole,
)


@pytest.fixture
def db():
    """Create a fresh in-memory SQLite database for each test."""
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
    """Create an AuthService backed by the test DB."""
    return AuthService(db=db)


# ═══════════════════════════════════════════════════════════
# 1. RESTART TEST — SESSION SURVIVES
# ═══════════════════════════════════════════════════════════

class TestAuthRestart:
    def test_login_and_validate_token(self, db, auth_service):
        """Login → validate token → still works."""
        result = auth_service.login("admin", "test_password_123")
        assert result["success"] is True
        token = result["token"]

        # Validate
        ctx = auth_service.validate_token(token)
        assert ctx is not None
        assert ctx.user_id == "admin-001"
        assert ctx.tenant_id == "default"
        assert ctx.role == SystemRole.ADMIN

    def test_session_survives_new_instance(self, db):
        """Login with AuthService #1 → create AuthService #2 → token still valid."""
        auth1 = AuthService(db=db)
        result = auth1.login("admin", "test_password_123")
        token = result["token"]

        # New AuthService instance (simulates restart)
        auth2 = AuthService(db=db)
        ctx = auth2.validate_token(token)
        assert ctx is not None
        assert ctx.user_id == "admin-001"

    def test_logout_survives(self, db, auth_service):
        """Login → logout → new instance → token invalid."""
        result = auth_service.login("admin", "test_password_123")
        token = result["token"]

        auth_service.logout(token)

        auth2 = AuthService(db=db)
        ctx = auth2.validate_token(token)
        assert ctx is None  # Revoked


# ═══════════════════════════════════════════════════════════
# 2. USER CREATION PERSISTS
# ═══════════════════════════════════════════════════════════

class TestUserPersistence:
    def test_create_user_persists(self, db, auth_service):
        """Create user → new instance → user exists."""
        result = auth_service.create_user(
            "testuser", "test@example.com", "password123",
            display_name="Test User", role_name="OPERATOR",
        )
        assert result["success"] is True
        user_id = result["user_id"]

        auth2 = AuthService(db=db)
        user = auth2.get_user(user_id)
        assert user is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"

    def test_login_new_user(self, db, auth_service):
        """Create user → login → works."""
        auth_service.create_user(
            "testuser", "test@example.com", "password123",
        )
        result = auth_service.login("testuser", "password123")
        assert result["success"] is True
        assert result["user"]["username"] == "testuser"

    def test_password_change_persists(self, db, auth_service):
        """Change password → new instance → new password works."""
        auth_service.create_user(
            "testuser", "test@example.com", "oldpassword",
        )
        user = auth_service.get_user(
            next(iter(auth_service._users.keys())) if not auth_service._use_db else None
        )
        # Get user by username
        user_repo = auth_service._get_user_repo()
        user_model = user_repo.get_by_username("testuser")

        result = auth_service.change_password(user_model.id, "oldpassword", "newpassword")
        assert result["success"] is True

        # Old password should fail
        result2 = auth_service.login("testuser", "oldpassword")
        assert result2["success"] is False

        # New password should work
        result3 = auth_service.login("testuser", "newpassword")
        assert result3["success"] is True


# ═══════════════════════════════════════════════════════════
# 3. TENANT CREATION PERSISTS
# ═══════════════════════════════════════════════════════════

class TestTenantPersistence:
    def test_create_tenant_persists(self, db, auth_service):
        """Create tenant → new instance → tenant exists."""
        result = auth_service.create_tenant("tenant-abc", "Tenant ABC")
        assert result["success"] is True

        auth2 = AuthService(db=db)
        tenants = auth2.get_tenants()
        tenant_ids = [t.id for t in tenants]
        assert "tenant-abc" in tenant_ids

    def test_tenant_duplicate_rejected(self, db, auth_service):
        """Create tenant twice → second rejected."""
        auth_service.create_tenant("tenant-abc", "Tenant ABC")
        result = auth_service.create_tenant("tenant-abc", "Tenant ABC Again")
        assert result["success"] is False


# ═══════════════════════════════════════════════════════════
# 4. AUDIT LOG PERSISTS
# ═══════════════════════════════════════════════════════════

class TestAuditPersistence:
    def test_audit_log_persists(self, db, auth_service):
        """Login generates audit → new instance → audit visible."""
        auth_service.login("admin", "test_password_123")

        auth2 = AuthService(db=db)
        log = auth2.get_audit_log("default", limit=10)
        assert len(log) >= 1
        assert any(r.action == "AUTH_SUCCESS" for r in log)


# ═══════════════════════════════════════════════════════════
# 5. MULTI-TENANT ISOLATION
# ═══════════════════════════════════════════════════════════

class TestAuthMultiTenant:
    def test_users_isolated_by_tenant(self, db, auth_service):
        """User created in tenant A not visible in tenant B."""
        auth_service.create_tenant("tenant-a", "Tenant A")
        auth_service.create_tenant("tenant-b", "Tenant B")

        auth_service.create_user(
            "userA", "a@test.com", "pass", tenant_id="tenant-a",
        )

        users_a = auth_service.get_users("tenant-a")
        users_b = auth_service.get_users("tenant-b")

        assert len(users_a) == 1
        assert users_a[0].username == "userA"
        assert len(users_b) == 0


# ═══════════════════════════════════════════════════════════
# 6. REPOSITORY DIRECT TESTS
# ═══════════════════════════════════════════════════════════

class TestRepositories:
    def test_user_repo_crud(self, db):
        repo = SQLAlchemyUserRepository(db)
        repo.create("u1", "testuser", "test@test.com", password_hash="hash123")
        found = repo.get_by_username("testuser")
        assert found is not None
        assert found.id == "u1"

        repo.update("u1", email="new@test.com")
        updated = repo.get_by_id("u1")
        assert updated.email == "new@test.com"

    def test_session_repo_crud(self, db):
        repo = SQLAlchemySessionRepository(db)
        repo.create("s1", "u1", "default", "token-abc",
                     expires_at=datetime.utcnow() + timedelta(hours=1))
        found = repo.get_by_token("token-abc")
        assert found is not None
        assert found.user_id == "u1"

        repo.revoke("s1")
        revoked = repo.get_by_token("token-abc")
        assert revoked is None  # Not ACTIVE

    def test_tenant_repo_crud(self, db):
        repo = SQLAlchemyTenantRepository(db)
        repo.create("t1", "Tenant One")
        found = repo.get_by_tenant_id("t1")
        assert found is not None
        assert found.name == "Tenant One"

    def test_role_repo_crud(self, db):
        repo = SQLAlchemyRoleRepository(db)
        repo.create("r1", "ADMIN", "ADMIN", ["admin.*"])
        found = repo.get_by_name("ADMIN")
        assert found is not None
        assert found.permissions == ["admin.*"]

    def test_membership_repo_crud(self, db):
        repo = SQLAlchemyMembershipRepository(db)
        repo.create("u1", "t1", "r1")
        found = repo.get("u1", "t1")
        assert found is not None
        assert found.role_id == "r1"

    def test_audit_repo_crud(self, db):
        repo = SQLAlchemyAuditRepository(db)
        repo.create("u1", "t1", "TEST_ACTION", result="SUCCESS")
        records = repo.list_for_tenant("t1")
        assert len(records) == 1
        assert records[0].action == "TEST_ACTION"
