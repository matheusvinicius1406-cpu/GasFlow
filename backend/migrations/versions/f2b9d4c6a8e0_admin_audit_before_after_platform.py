"""admin audit: before_json/after_json/platform no auth_audit_log

Revision ID: f2b9d4c6a8e0
Revises: e4f7a9b1c3d5
Create Date: 2026-09-12

P0 3.3: trilha de auditoria do admin console — estado anterior/posterior
das mutações sensíveis (usuários, roles, permissões) e plataforma de
origem. Aditivo; NULL em registros que não são mutação.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b9d4c6a8e0"
down_revision: Union[str, None] = "e4f7a9b1c3d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("auth_audit_log") as batch:
        batch.add_column(sa.Column("before_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("after_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("platform", sa.String(length=20), nullable=False, server_default=sa.text("''")))


def downgrade() -> None:
    with op.batch_alter_table("auth_audit_log") as batch:
        batch.drop_column("platform")
        batch.drop_column("after_json")
        batch.drop_column("before_json")
