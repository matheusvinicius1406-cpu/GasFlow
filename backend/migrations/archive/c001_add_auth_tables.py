"""add auth tables

Revision ID: c001
Revises: b001
Create Date: 2026-08-29
"""

from alembic import op
import sqlalchemy as sa

revision = "c001"
down_revision = "b001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── auth_users ──────────────────────────────────────
    op.create_table(
        "auth_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("email", sa.String(200), nullable=False, server_default=""),
        sa.Column("display_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("password_hash", sa.String(200), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("failed_login_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("username", name="uq_auth_user_username"),
        sa.Index("ix_auth_user_status", "status"),
    )

    # ── auth_sessions ───────────────────────────────────
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False, server_default="default"),
        sa.Column("token", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("last_seen_at", sa.DateTime, nullable=True),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(500), nullable=False, server_default=""),
        sa.UniqueConstraint("token", name="uq_auth_session_token"),
        sa.Index("ix_auth_session_user", "user_id"),
        sa.Index("ix_auth_session_status", "status"),
    )

    # ── auth_tenants ────────────────────────────────────
    op.create_table(
        "auth_tenants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", name="uq_auth_tenant_id"),
    )

    # ── auth_roles ──────────────────────────────────────
    op.create_table(
        "auth_roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("system_role", sa.String(30), nullable=False),
        sa.Column("permissions", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_auth_role_name"),
    )

    # ── auth_memberships ────────────────────────────────
    op.create_table(
        "auth_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("role_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_auth_membership_user_tenant"),
        sa.Index("ix_auth_membership_user", "user_id"),
        sa.Index("ix_auth_membership_tenant", "tenant_id"),
    )

    # ── auth_audit_log ──────────────────────────────────
    op.create_table(
        "auth_audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("actor_type", sa.String(20), nullable=False, server_default="USER"),
        sa.Column("tenant_id", sa.String(100), nullable=False, server_default=""),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource", sa.String(100), nullable=False, server_default=""),
        sa.Column("resource_id", sa.String(100), nullable=False, server_default=""),
        sa.Column("result", sa.String(20), nullable=False, server_default="SUCCESS"),
        sa.Column("timestamp", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("ip_address", sa.String(50), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(500), nullable=False, server_default=""),
        sa.Column("correlation_id", sa.String(36), nullable=True),
        sa.Column("details", sa.JSON, nullable=True),
        sa.Index("ix_auth_audit_tenant", "tenant_id"),
        sa.Index("ix_auth_audit_actor", "actor_id"),
        sa.Index("ix_auth_audit_timestamp", "timestamp"),
    )


def downgrade() -> None:
    op.drop_table("auth_audit_log")
    op.drop_table("auth_memberships")
    op.drop_table("auth_roles")
    op.drop_table("auth_tenants")
    op.drop_table("auth_sessions")
    op.drop_table("auth_users")
