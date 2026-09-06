"""
Security DB Models — FASE 13

SQLAlchemy models for identity, sessions, tenants, roles, audit.
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from app.infrastructure.database.base import Base


class UserModel(Base):
    __tablename__ = "security_users"

    id = Column(String(36), primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(200), unique=True, nullable=False, index=True)
    display_name = Column(String(200), nullable=True)
    password_hash = Column(String(500), nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE")
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SessionModel(Base):
    __tablename__ = "security_sessions"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("security_users.id"), nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    token = Column(String(200), unique=True, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)


class TenantModel(Base):
    __tablename__ = "security_tenants"

    id = Column(String(36), primary_key=True)
    name = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)


class TenantMembershipModel(Base):
    __tablename__ = "security_memberships"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("security_users.id"), nullable=False, index=True)
    tenant_id = Column(String(36), ForeignKey("security_tenants.id"), nullable=False, index=True)
    role_id = Column(String(36), ForeignKey("security_roles.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_membership_user_tenant"),)


class RoleModel(Base):
    __tablename__ = "security_roles"

    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False)
    system_role = Column(String(30), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class RolePermissionModel(Base):
    __tablename__ = "security_role_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(String(36), ForeignKey("security_roles.id"), nullable=False, index=True)
    permission = Column(String(100), nullable=False)  # e.g., "customer.read"

    __table_args__ = (UniqueConstraint("role_id", "permission", name="uq_role_permission"),)


class AuditRecordModel(Base):
    __tablename__ = "security_audit"

    id = Column(String(36), primary_key=True)
    actor_id = Column(String(36), nullable=False, index=True)
    actor_type = Column(String(20), nullable=False, default="USER")
    tenant_id = Column(String(36), nullable=False, index=True)
    action = Column(String(50), nullable=False, index=True)
    resource = Column(String(50), nullable=True)
    resource_id = Column(String(100), nullable=True)
    result = Column(String(20), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    correlation_id = Column(String(100), nullable=True)
    details_json = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_audit_tenant_action", "tenant_id", "action"),
        Index("ix_audit_actor", "actor_id", "actor_type"),
    )
