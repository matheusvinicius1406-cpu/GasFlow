"""driver location history — histórico append-only de posições

`driver_locations` continua sendo a "última posição" (upsert) para não quebrar
quem já lê dela. Esta tabela nova é o log imutável de posições, base para
distância percorrida, replay do dia, geofencing e ETA.

`driver_id` guarda `delivery_drivers.codigo` (String), a mesma identidade usada
por `driver_locations`, `delivery_records` e pelo canal WS `driver:{id}` — por
isso não é o `id` serial do entregador nem uma FK simples (o codigo só é único
por tenant).

Variante com PostGIS (opcional): substituir `latitude`/`longitude` por
`geography(POINT, 4326)` + índice GiST. A versão sem PostGIS é a padrão e a
única exigida.

Revision ID: e7b1c3d5f9a2
Revises: c2d8e4f6a1b3
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa
from typing import Union


revision: str = "e7b1c3d5f9a2"
down_revision: Union[str, None] = "c2d8e4f6a1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "driver_location_history",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("driver_id", sa.String(length=36), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.Column("speed_kmh", sa.Float(), nullable=True),
        sa.Column("heading_deg", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_driver_loc_hist_tenant_id", "driver_location_history", ["tenant_id"])
    op.create_index("ix_driver_loc_hist_driver_id", "driver_location_history", ["driver_id"])
    op.create_index("ix_driver_loc_hist_recorded_at", "driver_location_history", ["recorded_at"])
    op.create_index(
        "ix_driver_loc_hist_driver_time",
        "driver_location_history",
        ["driver_id", "recorded_at"],
    )
    op.create_index(
        "ix_driver_loc_hist_tenant_time",
        "driver_location_history",
        ["tenant_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_driver_loc_hist_tenant_time", table_name="driver_location_history")
    op.drop_index("ix_driver_loc_hist_driver_time", table_name="driver_location_history")
    op.drop_index("ix_driver_loc_hist_recorded_at", table_name="driver_location_history")
    op.drop_index("ix_driver_loc_hist_driver_id", table_name="driver_location_history")
    op.drop_index("ix_driver_loc_hist_tenant_id", table_name="driver_location_history")
    op.drop_table("driver_location_history")
