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

Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class AuthUserModel(Base):
    """Persistent user record — replaces in-memory _users dict."""

    __tablename__ = "auth_users"

    __table_args__ = (
        UniqueConstraint("username", name="uq_auth_user_username"),
        Index("ix_auth_user_status", "status"),
        # Vínculo com entregador: quando presente, nunca vazio. A equivalência
        # completa (role==DRIVER ⟺ driver_id IS NOT NULL) é validada no serviço
        # — o role vive em auth_roles (relacional), fora do alcance de um CHECK.
        CheckConstraint("driver_id IS NULL OR driver_id <> ''", name="ck_auth_user_driver_id_nonempty"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")  # ACTIVE, DISABLED, LOCKED
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # P0 RBAC: role persistido + fluxo de senha temporária.
    role_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )  # → auth_roles.id (None = legacy single-admin)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)  # admin que criou o usuário
    # Entregador: guarda `delivery_drivers.codigo` (identidade usada em todo o
    # grafo — delivery_records.driver_id, driver_stock e canal WS driver:{id}).
    driver_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuthSessionModel(Base):
    """Persistent session record — replaces in-memory _sessions dict."""

    __tablename__ = "auth_sessions"

    __table_args__ = (
        UniqueConstraint("token", name="uq_auth_session_token"),
        Index("ix_auth_session_user", "user_id"),
        Index("ix_auth_session_status", "status"),
        Index("ix_auth_session_refresh_hash", "refresh_token_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, default="default")
    token: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")  # ACTIVE, REVOKED, EXPIRED
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ip_address: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Operator JWT (B5): a própria sessão é a família do refresh token.
    # `refresh_prev_hash` existe só para detectar reuso do refresh rotacionado.
    refresh_token_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    refresh_prev_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    refresh_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    refresh_rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    platform: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # desktop | mobile


class AuthTenantModel(Base):
    """Persistent tenant record — replaces in-memory _tenants dict."""

    __tablename__ = "auth_tenants"

    __table_args__ = (UniqueConstraint("tenant_id", name="uq_auth_tenant_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AuthRoleModel(Base):
    """Persistent role record — replaces in-memory _roles dict."""

    __tablename__ = "auth_roles"

    __table_args__ = (UniqueConstraint("name", name="uq_auth_role_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    system_role: Mapped[str] = mapped_column(String(30), nullable=False)  # ADMIN, MANAGER, OPERATOR, etc.
    permissions: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AuthMembershipModel(Base):
    """Persistent user-tenant-role membership — replaces in-memory _memberships list."""

    __tablename__ = "auth_memberships"

    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_auth_membership_user_tenant"),
        Index("ix_auth_membership_user", "user_id"),
        Index("ix_auth_membership_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    role_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AuthAuditModel(Base):
    """Persistent audit log — replaces in-memory _audit_log list."""

    __tablename__ = "auth_audit_log"

    __table_args__ = (
        Index("ix_auth_audit_tenant", "tenant_id"),
        Index("ix_auth_audit_actor", "actor_id"),
        Index("ix_auth_audit_timestamp", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="USER")
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    result: Mapped[str] = mapped_column(String(20), nullable=False, default="SUCCESS")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    correlation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    details: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # P0 3.3: estado anterior/posterior da mutação (snapshot sem segredos) —
    # preenchidos pelos endpoints admin; None em eventos simples (login etc.).
    before_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    after_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, default="")  # desktop | mobile | web | api
