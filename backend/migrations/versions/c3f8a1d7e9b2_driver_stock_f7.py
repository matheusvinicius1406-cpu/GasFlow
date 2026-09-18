"""driver_stock: estoque carregado pelo entregador (F7)

Revision ID: c3f8a1d7e9b2
Revises: b7d3e9f2a4c8
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa
from typing import Union


revision: str = "c3f8a1d7e9b2"
down_revision: Union[str, None] = "b7d3e9f2a4c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "driver_stock",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="default"),
        sa.Column("driver_id", sa.String(length=36), nullable=False),
        sa.Column("product_codigo", sa.String(length=20), nullable=False),
        sa.Column("full_tanks_loaded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("empty_tanks_returned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("blocked_reason", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "driver_id", "product_codigo", name="uq_driver_stock_driver_product"),
    )
    op.create_index("ix_driver_stock_tenant_id", "driver_stock", ["tenant_id"])
    op.create_index("ix_driver_stock_driver_id", "driver_stock", ["driver_id"])
    op.create_index("ix_driver_stock_tenant_driver", "driver_stock", ["tenant_id", "driver_id"])

    op.create_table(
        "driver_stock_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="default"),
        sa.Column("driver_id", sa.String(length=36), nullable=False),
        sa.Column("product_codigo", sa.String(length=20), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("reference_type", sa.String(length=30), nullable=True),
        sa.Column("reference_id", sa.String(length=36), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("balance_after_loaded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("balance_after_empty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_driver_stock_events_tenant_id", "driver_stock_events", ["tenant_id"])
    op.create_index("ix_driver_stock_events_driver", "driver_stock_events", ["tenant_id", "driver_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_driver_stock_events_driver", table_name="driver_stock_events")
    op.drop_index("ix_driver_stock_events_tenant_id", table_name="driver_stock_events")
    op.drop_table("driver_stock_events")
    op.drop_index("ix_driver_stock_tenant_driver", table_name="driver_stock")
    op.drop_index("ix_driver_stock_driver_id", table_name="driver_stock")
    op.drop_index("ix_driver_stock_tenant_id", table_name="driver_stock")
    op.drop_table("driver_stock")
