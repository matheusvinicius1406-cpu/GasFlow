"""
Auth Persistence Models — SQLAlchemy models for authentication.

Replaces in-memory AuthService storage with database persistence.
Single source of truth for users, sessions, tenants, roles, and audit.

Models:
- AuthUserModel: users table
- AuthSessionModel: auth_sessions table
- AuthTenantModel: auth_tenants table
- AuthRoleModel: auth_roles table
- AuthMembershipModel: auth_memberships table
- AuthAuditModel: auth_audit_log table
"""

from sqlalchemy import Boolean, Column, Integer, String, DateTime, JSON, Index, UniqueConstraint
from datetime import datetime
from app.infrastructure.database.base import Base


class AuthUserModel(Base):
    """Persistent user record — replaces in-memory _users dict."""

    __tablename__ = "auth_users"

    __table_args__ = (
        UniqueConstraint("username", name="uq_auth_user_username"),
        Index("ix_auth_user_status", "status"),
    )

    id = Column(String(36), primary_key=True)
    username = Column(String(100), nullable=False)
    email = Column(String(200), nullable=False, default="")
    display_name = Column(String(200), nullable=False, default="")
    password_hash = Column(String(200), nullable=False, default="")
    status = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE, DISABLED, LOCKED
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime, nullable=True)
    # P0 RBAC: role persistido + fluxo de senha temporária.
    role_id = Column(String(36), nullable=True)  # → auth_roles.id (None = legacy single-admin)
    must_change_password = Column(Boolean, nullable=False, default=False)
    last_login_at = Column(DateTime, nullable=True)
    created_by = Column(String(36), nullable=True)  # admin que criou o usuário
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuthSessionModel(Base):
    """Persistent session record — replaces in-memory _sessions dict."""

    __tablename__ = "auth_sessions"

    __table_args__ = (
        UniqueConstraint("token", name="uq_auth_session_token"),
        Index("ix_auth_session_user", "user_id"),
        Index("ix_auth_session_status", "status"),
    )

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False)
    tenant_id = Column(String(100), nullable=False, default="default")
    token = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE, REVOKED, EXPIRED
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    ip_address = Column(String(50), nullable=False, default="")
    user_agent = Column(String(500), nullable=False, default="")


class AuthTenantModel(Base):
    """Persistent tenant record — replaces in-memory _tenants dict."""

    __tablename__ = "auth_tenants"

    __table_args__ = (UniqueConstraint("tenant_id", name="uq_auth_tenant_id"),)

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(100), nullable=False)
    name = Column(String(200), nullable=False, default="")
    status = Column(String(20), nullable=False, default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuthRoleModel(Base):
    """Persistent role record — replaces in-memory _roles dict."""

    __tablename__ = "auth_roles"

    __table_args__ = (UniqueConstraint("name", name="uq_auth_role_name"),)

    id = Column(String(36), primary_key=True)
    name = Column(String(50), nullable=False)
    system_role = Column(String(30), nullable=False)  # ADMIN, MANAGER, OPERATOR, etc.
    permissions = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuthMembershipModel(Base):
    """Persistent user-tenant-role membership — replaces in-memory _memberships list."""

    __tablename__ = "auth_memberships"

    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_auth_membership_user_tenant"),
        Index("ix_auth_membership_user", "user_id"),
        Index("ix_auth_membership_tenant", "tenant_id"),
    )

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False)
    tenant_id = Column(String(100), nullable=False)
    role_id = Column(String(36), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuthAuditModel(Base):
    """Persistent audit log — replaces in-memory _audit_log list."""

    __tablename__ = "auth_audit_log"

    __table_args__ = (
        Index("ix_auth_audit_tenant", "tenant_id"),
        Index("ix_auth_audit_actor", "actor_id"),
        Index("ix_auth_audit_timestamp", "timestamp"),
    )

    id = Column(String(36), primary_key=True)
    actor_id = Column(String(36), nullable=False, default="")
    actor_type = Column(String(20), nullable=False, default="USER")
    tenant_id = Column(String(100), nullable=False, default="")
    action = Column(String(50), nullable=False)
    resource = Column(String(100), nullable=False, default="")
    resource_id = Column(String(100), nullable=False, default="")
    result = Column(String(20), nullable=False, default="SUCCESS")
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip_address = Column(String(50), nullable=False, default="")
    user_agent = Column(String(500), nullable=False, default="")
    correlation_id = Column(String(36), nullable=True)
    details = Column(JSON, nullable=True)
