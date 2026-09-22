"""driver credentials — vínculo auth_users ↔ delivery_drivers

O entregador passa a autenticar pelo `/auth/login` (auth principal), herdando o
gate de `must_change_password` no HTTP e no WebSocket. Para isso, a credencial
(`auth_users`) ganha `driver_id`, apontando para a entidade de negócio já
existente (`delivery_drivers`) — não há tabela nova de motorista.

`driver_id` guarda `delivery_drivers.codigo`, que é a identidade usada em todo
o grafo operacional (`delivery_records.driver_id`, `driver_stock.driver_id` e o
canal `driver:{id}` do WebSocket) — por isso não é o `id` serial do driver.

Revision ID: c2d8e4f6a1b3
Revises: a4c8e2f6b1d3
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa
from typing import Union


revision: str = "c2d8e4f6a1b3"
down_revision: Union[str, None] = "a4c8e2f6b1d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite não faz ALTER TABLE completo — batch recria a tabela.
    with op.batch_alter_table("auth_users", schema=None) as batch:
        batch.add_column(sa.Column("driver_id", sa.String(length=36), nullable=True))
        batch.create_index("ix_auth_user_driver_id", ["driver_id"])
        batch.create_check_constraint(
            "ck_auth_user_driver_id_nonempty",
            "driver_id IS NULL OR driver_id <> ''",
        )

    with op.batch_alter_table("delivery_drivers", schema=None) as batch:
        batch.add_column(sa.Column("document", sa.String(), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("delivery_drivers", schema=None) as batch:
        batch.drop_column("updated_at")
        batch.drop_column("document")

    with op.batch_alter_table("auth_users", schema=None) as batch:
        batch.drop_constraint("ck_auth_user_driver_id_nonempty", type_="check")
        batch.drop_index("ix_auth_user_driver_id")
        batch.drop_column("driver_id")
