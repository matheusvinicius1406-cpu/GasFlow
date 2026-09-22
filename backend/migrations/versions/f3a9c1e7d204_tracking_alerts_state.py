"""tracking alerts state + tracking epoch (correções do rastreio)

Dois problemas reais corrigidos aqui:

1. **Alerta piscando o dia inteiro.** `TrackingAlertsService` publicava
   `driver.alert` a cada lote de ingestão enquanto a condição valesse. Agora
   existe cooldown por `(tenant, driver, kind)` — e para isso o estado precisa
   sobreviver a restart, logo vai para o banco (`tracking_alert_state`).
2. **Link público sem teto nem revogação.** O token carregava só a expiração.
   `delivery_drivers.tracking_epoch` permite revogar **todos** os links de um
   entregador de uma vez: o token embute a epoch vigente e o snapshot recusa
   (410) quando ela diverge.

Revision ID: f3a9c1e7d204
Revises: e7b1c3d5f9a2
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa
from typing import Union


revision: str = "f3a9c1e7d204"
down_revision: Union[str, None] = "e7b1c3d5f9a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite não faz ALTER completo — batch recria a tabela.
    with op.batch_alter_table("delivery_drivers", schema=None) as batch:
        batch.add_column(
            sa.Column(
                "tracking_epoch",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    op.create_table(
        "tracking_alert_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("driver_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "driver_id", "kind", name="uq_tracking_alert_state"),
    )
    op.create_index("ix_tracking_alert_state_tenant", "tracking_alert_state", ["tenant_id"])
    op.create_index("ix_tracking_alert_state_driver", "tracking_alert_state", ["driver_id"])


def downgrade() -> None:
    op.drop_index("ix_tracking_alert_state_driver", table_name="tracking_alert_state")
    op.drop_index("ix_tracking_alert_state_tenant", table_name="tracking_alert_state")
    op.drop_table("tracking_alert_state")

    with op.batch_alter_table("delivery_drivers", schema=None) as batch:
        batch.drop_column("tracking_epoch")
