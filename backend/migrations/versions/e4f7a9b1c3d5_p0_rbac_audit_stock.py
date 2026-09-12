"""P0: RBAC persistido (permissions, matriz, overrides) + estoque cheios/vazios + snapshot diário

Revision ID: e4f7a9b1c3d5
Revises: d1e5a7c3b2f8
Create Date: 2026-09-12

Conteúdo (roadmap multimodal — Fase 2, decisões A=aditivo e B2=reserva+troca):
- RBAC: tabela `permissions` (catálogo `resource.action`), `role_permissions`
  (matriz normalizada espelhando ROLE_PERMISSIONS), `user_permissions_override`
  e colunas novas em `auth_users` (role_id, must_change_password, last_login_at,
  created_by). `auth_roles`/`auth_audit_log` JÁ EXISTEM e seguem como fonte —
  sem tabelas paralelas.
- Estoque (Decisão A — aditivo): `inventory.quantity_full/quantity_empty`
  (backfill full=quantity, empty=0) e `stock_movements.quantity_full_delta/
  quantity_empty_delta`.
- Snapshot: `stock_daily_snapshots` (idempotente por tenant+data+produto).
- Seed: catálogo de permissões + roles de sistema (auth_roles) + matriz a
  partir de ROLE_PERMISSIONS (código = fallback, banco = fonte). A seed vive
  em app/infrastructure/database/rbac_seed.py (fonte única compartilhada com
  o boot do Desktop — que cobre bancos legados carimbados, onde esta
  migration não roda).
- SQLite: todas as alterações de tabela existente via batch_alter_table.

Downgrade: implementado por completo — drop das tabelas novas, reversão das
colunas e restauração do backfill (quantity = quantity_full antes do drop).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4f7a9b1c3d5"
down_revision: Union[str, None] = "d1e5a7c3b2f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# A seed (catálogo PERMISSIONS + matriz ROLE_MATRIX) vive em
# app/infrastructure/database/rbac_seed.py — fonte única compartilhada com o
# boot do Desktop, que também precisa populá-la em bancos legados carimbados
# (nestes, esta migration não roda — só o stamp).


def upgrade() -> None:
    # ── 1. RBAC: catálogo + matriz + overrides ──────────────────────────
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("module", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    with op.batch_alter_table("permissions") as batch:
        batch.create_index("ix_permissions_module", ["module"])
        batch.create_unique_constraint("uq_permissions_code", ["code"])

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.String(length=36), primary_key=True),
        sa.Column("permission_id", sa.Integer(), primary_key=True),
    )
    with op.batch_alter_table("role_permissions") as batch:
        batch.create_index("ix_role_permissions_role", ["role_id"])
        batch.create_unique_constraint("uq_role_permissions_role_permission", ["role_id", "permission_id"])

    op.create_table(
        "user_permissions_override",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    with op.batch_alter_table("user_permissions_override") as batch:
        batch.create_index("ix_user_perm_override_user", ["user_id"])
        batch.create_unique_constraint("uq_user_perm_override_user_permission", ["user_id", "permission_id"])

    # ── 2. auth_users: extensões P0 ─────────────────────────────────────
    with op.batch_alter_table("auth_users") as batch:
        batch.add_column(sa.Column("role_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("created_by", sa.String(length=36), nullable=True))

    # ── 3. Estoque: cheios/vazios (Decisão A — aditivo) ─────────────────
    with op.batch_alter_table("inventory") as batch:
        batch.add_column(sa.Column("quantity_full", sa.Integer(), nullable=False, server_default=sa.text("0")))
        batch.add_column(sa.Column("quantity_empty", sa.Integer(), nullable=False, server_default=sa.text("0")))
    # Backfill: full = quantity (total atual = cheios no fluxo atual), empty = 0.
    op.execute("UPDATE inventory SET quantity_full = quantity, quantity_empty = 0")

    with op.batch_alter_table("stock_movements") as batch:
        batch.add_column(sa.Column("quantity_full_delta", sa.Integer(), nullable=False, server_default=sa.text("0")))
        batch.add_column(sa.Column("quantity_empty_delta", sa.Integer(), nullable=False, server_default=sa.text("0")))

    # ── 4. Snapshot diário ──────────────────────────────────────────────
    op.create_table(
        "stock_daily_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("product_codigo", sa.String(length=100), nullable=False),
        sa.Column("initial_full", sa.Integer(), nullable=False),
        sa.Column("initial_empty", sa.Integer(), nullable=False),
        sa.Column("closing_full", sa.Integer(), nullable=False),
        sa.Column("closing_empty", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    with op.batch_alter_table("stock_daily_snapshots") as batch:
        batch.create_index("ix_stock_snapshot_date", ["snapshot_date"])
        batch.create_index("ix_stock_snapshot_product", ["product_codigo"])
        batch.create_unique_constraint(
            "uq_stock_snapshot_tenant_date_product", ["tenant_id", "snapshot_date", "product_codigo"]
        )

    # ── 5. Seed RBAC (fonte única: rbac_seed) ───────────────────────────
    from app.infrastructure.database.rbac_seed import seed_rbac

    conn = op.get_bind()
    seed_rbac(conn)


def downgrade() -> None:
    # ── RBAC ────────────────────────────────────────────────────────────
    op.drop_table("user_permissions_override")
    op.drop_table("role_permissions")
    op.drop_table("permissions")

    with op.batch_alter_table("auth_users") as batch:
        batch.drop_column("created_by")
        batch.drop_column("last_login_at")
        batch.drop_column("must_change_password")
        batch.drop_column("role_id")

    # ── Estoque: restaura quantity a partir do backfill e reverte colunas ─
    op.execute("UPDATE inventory SET quantity = quantity_full WHERE quantity_full IS NOT NULL")
    with op.batch_alter_table("inventory") as batch:
        batch.drop_column("quantity_empty")
        batch.drop_column("quantity_full")
    with op.batch_alter_table("stock_movements") as batch:
        batch.drop_column("quantity_empty_delta")
        batch.drop_column("quantity_full_delta")

    op.drop_table("stock_daily_snapshots")
