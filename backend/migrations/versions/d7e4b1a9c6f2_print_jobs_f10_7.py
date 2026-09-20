"""print_jobs: fila de impressão persistida (F10.7)

Revision ID: d7e4b1a9c6f2
Revises: c3f8a1d7e9b2
Create Date: 2026-09-20
"""

from alembic import op
import sqlalchemy as sa
from typing import Union


revision: str = "d7e4b1a9c6f2"
down_revision: Union[str, None] = "c3f8a1d7e9b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "print_jobs",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="default"),
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("is_reprint", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requested_by", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", sa.LargeBinary(), nullable=True),
        sa.Column("printer_name", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_print_jobs_tenant_id", "print_jobs", ["tenant_id"])
    op.create_index("ix_print_jobs_order_id", "print_jobs", ["order_id"])
    op.create_index("ix_print_jobs_status", "print_jobs", ["status"])
    op.create_index("ix_print_jobs_created_at", "print_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_print_jobs_created_at", table_name="print_jobs")
    op.drop_index("ix_print_jobs_status", table_name="print_jobs")
    op.drop_index("ix_print_jobs_order_id", table_name="print_jobs")
    op.drop_index("ix_print_jobs_tenant_id", table_name="print_jobs")
    op.drop_table("print_jobs")
