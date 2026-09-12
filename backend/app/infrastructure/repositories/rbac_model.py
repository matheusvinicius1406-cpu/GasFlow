"""
RBAC Persistence Models — P0 (roadmap multimodal)

Complementa auth_model.py (AuthUserModel/AuthRoleModel já existentes):
- PermissionModel: catálogo normalizado de permissões (resource.action)
- RolePermissionModel: matriz role → permissão (banco = fonte, código = fallback)
- UserPermissionOverrideModel: concessões/revogações por usuário
- StockDailySnapshotModel: estoque inicial/fechamento do dia por produto

Convenção de permissão: `resource.action` (padrão existente do domínio
de segurança — ex.: user.create, inventory.adjust, admin.*).
"""

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, UniqueConstraint, Index
from datetime import datetime

from app.infrastructure.database.base import Base


class PermissionModel(Base):
    """Catálogo de permissões — code no formato `resource.action`."""

    __tablename__ = "permissions"

    __table_args__ = (
        UniqueConstraint("code", name="uq_permissions_code"),
        Index("ix_permissions_module", "module"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(100), nullable=False)
    description = Column(String(200), nullable=False, default="")
    module = Column(String(50), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RolePermissionModel(Base):
    """Matriz role ↔ permissão (normalizada; espelha ROLE_PERMISSIONS)."""

    __tablename__ = "role_permissions"

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
        Index("ix_role_permissions_role", "role_id"),
    )

    role_id = Column(String(36), primary_key=True)  # → auth_roles.id
    permission_id = Column(Integer, primary_key=True)  # → permissions.id


class UserPermissionOverrideModel(Base):
    """Override por usuário: granted=True concede além do role,
    granted=False revoga permissão herdada."""

    __tablename__ = "user_permissions_override"

    __table_args__ = (
        UniqueConstraint("user_id", "permission_id", name="uq_user_perm_override_user_permission"),
        Index("ix_user_perm_override_user", "user_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), nullable=False)  # → auth_users.id
    permission_id = Column(Integer, nullable=False)  # → permissions.id
    granted = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StockDailySnapshotModel(Base):
    """Snapshot diário de estoque (cheios/vazios) — início e fechamento do dia.

    Idempotente por (tenant, data, produto): o job diário faz upsert.
    """

    __tablename__ = "stock_daily_snapshots"

    __table_args__ = (
        UniqueConstraint("tenant_id", "snapshot_date", "product_codigo", name="uq_stock_snapshot_tenant_date_product"),
        Index("ix_stock_snapshot_date", "snapshot_date"),
        Index("ix_stock_snapshot_product", "product_codigo"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(100), nullable=False, default="default")
    snapshot_date = Column(Date, nullable=False)
    product_codigo = Column(String(100), nullable=False)
    initial_full = Column(Integer, nullable=False, default=0)
    initial_empty = Column(Integer, nullable=False, default=0)
    closing_full = Column(Integer, nullable=False, default=0)
    closing_empty = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
