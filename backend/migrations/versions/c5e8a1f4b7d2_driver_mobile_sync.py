"""driver mobile: refresh tokens (rotação) + offline sync log (delta sync)

Revision ID: c5e8a1f4b7d2
Revises: b3a7c9e1d5f4
Create Date: 2026-09-14

App do Entregador — Fase 1:
- driver_refresh_tokens: refresh 7d com rotação; family_id liga a cadeia e
  reuso de token ROTATED revoga a família inteira (anti-replay).
- offline_sync_log: log de mudanças por entidade para o delta sync do
  mobile (GET /driver/sync?since=). Purga junto do retention de 90 dias.
Aditivo; idempotente no boot via create_all.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5e8a1f4b7d2"
down_revision: Union[str, None] = "b3a7c9e1d5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "driver_refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token", sa.String(length=64), nullable=False),  # sha256 do token — literal nunca persistido
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("driver_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="default"),
        sa.Column("status", sa.String(length=20), server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("token", name="uq_driver_refresh_token"),
    )
    op.create_index("ix_driver_refresh_family", "driver_refresh_tokens", ["family_id"])
    op.create_index("ix_driver_refresh_driver", "driver_refresh_tokens", ["driver_id"])

    op.create_table(
        "offline_sync_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="default"),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sync_log_tenant_time", "offline_sync_log", ["tenant_id", "changed_at"])


def downgrade() -> None:
    op.drop_index("ix_sync_log_tenant_time", table_name="offline_sync_log")
    op.drop_table("offline_sync_log")
    op.drop_index("ix_driver_refresh_driver", table_name="driver_refresh_tokens")
    op.drop_index("ix_driver_refresh_family", table_name="driver_refresh_tokens")
    op.drop_table("driver_refresh_tokens")
