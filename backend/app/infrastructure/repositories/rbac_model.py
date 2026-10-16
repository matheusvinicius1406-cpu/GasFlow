"""
RBAC Persistence Models — P0 (roadmap multimodal)

Complementa auth_model.py (AuthUserModel/AuthRoleModel já existentes):
- PermissionModel: catálogo normalizado de permissões (resource.action)
- RolePermissionModel: matriz role → permissão (banco = fonte, código = fallback)
- UserPermissionOverrideModel: concessões/revogações por usuário
- StockDailySnapshotModel: estoque inicial/fechamento do dia por produto

Convenção de permissão: `resource.action` (padrão existente do domínio
de segurança — ex.: user.create, inventory.adjust, admin.*).

Estilo SQLAlchemy 2.0 tipado (`Mapped[...]`): a nullability da anotação
reproduz a do modelo legado/Alembic.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class PermissionModel(Base):
    """Catálogo de permissões — code no formato `resource.action`."""

    __tablename__ = "permissions"

    __table_args__ = (
        UniqueConstraint("code", name="uq_permissions_code"),
        Index("ix_permissions_module", "module"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    module: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class RolePermissionModel(Base):
    """Matriz role ↔ permissão (normalizada; espelha ROLE_PERMISSIONS)."""

    __tablename__ = "role_permissions"

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
        Index("ix_role_permissions_role", "role_id"),
    )

    role_id: Mapped[str] = mapped_column(String(36), primary_key=True)  # → auth_roles.id
    permission_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # → permissions.id


class UserPermissionOverrideModel(Base):
    """Override por usuário: granted=True concede além do role,
    granted=False revoga permissão herdada."""

    __tablename__ = "user_permissions_override"

    __table_args__ = (
        UniqueConstraint("user_id", "permission_id", name="uq_user_perm_override_user_permission"),
        Index("ix_user_perm_override_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)  # → auth_users.id
    permission_id: Mapped[int] = mapped_column(Integer, nullable=False)  # → permissions.id
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, default="default")
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    product_codigo: Mapped[str] = mapped_column(String(100), nullable=False)
    initial_full: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    initial_empty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    closing_full: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    closing_empty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
