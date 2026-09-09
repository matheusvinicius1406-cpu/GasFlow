"""integrations, imported_orders e sync_logs (46 tabelas)

Revision ID: c8d4e2f6a9b1
Revises: a7c1e9f2b4d6
Create Date: 2026-09-06

Nova revision (não autogerada) — espelha exatamente os models:
- integrations (IntegrationModel)
- imported_orders (ImportedOrderModel)
- sync_logs (SyncLogModel)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d4e2f6a9b1"
down_revision: Union[str, None] = "a7c1e9f2b4d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("auth_type", sa.String(length=20), nullable=False),
        sa.Column("auth_config", sa.JSON(), nullable=True),
        sa.Column("import_token", sa.String(length=64), nullable=False),
        sa.Column("field_mapping", sa.JSON(), nullable=True),
        sa.Column("selectors", sa.JSON(), nullable=True),
        sa.Column("orders_path", sa.String(length=200), nullable=True),
        sa.Column("sync_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_status", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_token"),
    )
    with op.batch_alter_table("integrations", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_integrations_tenant_id"), ["tenant_id"], unique=False)

    op.create_table(
        "imported_orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("integration_id", sa.String(length=36), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("external_data", sa.JSON(), nullable=True),
        sa.Column("order_data", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("gasflow_order_codigo", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("imported_orders", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_imported_orders_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_imported_orders_integration_id"), ["integration_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_imported_orders_external_id"), ["external_id"], unique=False)

    op.create_table(
        "sync_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("integration_id", sa.String(length=36), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("total_found", sa.Integer(), nullable=False),
        sa.Column("total_imported", sa.Integer(), nullable=False),
        sa.Column("total_errors", sa.Integer(), nullable=False),
        sa.Column("error_details", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("sync_logs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sync_logs_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_sync_logs_integration_id"), ["integration_id"], unique=False)


def downgrade() -> None:
    op.drop_table("sync_logs")
    op.drop_table("imported_orders")
    op.drop_table("integrations")
