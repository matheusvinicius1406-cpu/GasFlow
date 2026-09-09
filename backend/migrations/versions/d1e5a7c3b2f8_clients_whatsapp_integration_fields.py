"""clients: campos de integração WhatsApp (sync/reativação/enriquecimento)

Revision ID: d1e5a7c3b2f8
Revises: c8d4e2f6a9b1
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa
from typing import Union


revision: str = "d1e5a7c3b2f8"
down_revision: Union[str, None] = "c8d4e2f6a9b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("has_name", sa.Boolean(), nullable=True))
    op.add_column("clients", sa.Column("is_whatsapp", sa.Boolean(), nullable=True))
    op.add_column("clients", sa.Column("last_interaction_at", sa.DateTime(), nullable=True))
    op.add_column("clients", sa.Column("last_sync_at", sa.DateTime(), nullable=True))
    op.add_column("clients", sa.Column("marketing_status", sa.String(20), nullable=True))
    op.create_index("ix_clients_last_interaction", "clients", ["last_interaction_at"])
    op.create_index("ix_clients_marketing_status", "clients", ["marketing_status"])


def downgrade() -> None:
    op.drop_index("ix_clients_marketing_status", table_name="clients")
    op.drop_index("ix_clients_last_interaction", table_name="clients")
    op.drop_column("clients", "marketing_status")
    op.drop_column("clients", "last_sync_at")
    op.drop_column("clients", "last_interaction_at")
    op.drop_column("clients", "is_whatsapp")
    op.drop_column("clients", "has_name")
