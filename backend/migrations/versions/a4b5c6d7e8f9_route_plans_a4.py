"""A4: persistir plano de rota otimizado (route_plan_records)

Revision ID: a4b5c6d7e8f9
Revises: c1a2b3d4e5f6
Create Date: 2026-10-19

O resultado da otimização de rota (Fase 8) era efêmero: HTTP response +
evento em memória. Reiniciar o backend perdia a ordem otimizada e o
motorista recebia o evento perdido. A4 persiste o último plano por
(tenant_id, driver_id) — upsert; tabela só recebe linhas quando
DELIVERY_SMART_ROUTING_ENABLED=true (flag default false).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "c1a2b3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "route_plan_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("driver_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("input_delivery_ids", sa.JSON(), nullable=True),
        sa.Column("ordered_delivery_ids", sa.JSON(), nullable=False),
        sa.Column("total_distance_km", sa.Float(), nullable=False),
        sa.Column("total_duration_s", sa.Integer(), nullable=False),
        sa.Column("improvement_km", sa.Float(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("geometry", sa.JSON(), nullable=True),
        sa.Column("changed", sa.Integer(), nullable=False),
        sa.Column("origin_lat", sa.Float(), nullable=True),
        sa.Column("origin_lng", sa.Float(), nullable=True),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "driver_id", name="uq_route_plan_tenant_driver"),
    )
    op.create_index("ix_route_plan_tenant", "route_plan_records", ["tenant_id"])
    op.create_index("ix_route_plan_driver", "route_plan_records", ["driver_id"])


def downgrade() -> None:
    op.drop_index("ix_route_plan_driver", table_name="route_plan_records")
    op.drop_index("ix_route_plan_tenant", table_name="route_plan_records")
    op.drop_table("route_plan_records")
