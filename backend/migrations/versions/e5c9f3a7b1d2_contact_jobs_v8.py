"""contact_jobs: job persistido do renomeador de contatos (Fase 2 §5/§9 etapa 8)

Revision ID: e5c9f3a7b1d2
Revises: d4e8b2c6f1a3
Create Date: 2026-09-29

O renomeador em lote é bounded-batch: cada request processa uma faixa e o job
retoma pelo cursor (`codigo`/`id`, keyset) — por isso o estado vive em tabela,
não em memória do processo (que um restart perderia).

Aditiva: só cria tabela nova, não toca em `clients` nem em `geocode_cache`.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5c9f3a7b1d2"
down_revision: Union[str, None] = "d4e8b2c6f1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contact_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("cursor", sa.String(length=64), nullable=True),
        sa.Column("regra", sa.JSON(), nullable=True),
        sa.Column("filtro", sa.JSON(), nullable=True),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("processados", sa.Integer(), nullable=False),
        sa.Column("alterados", sa.Integer(), nullable=False),
        sa.Column("metrica", sa.JSON(), nullable=True),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contact_jobs_tenant_id", "contact_jobs", ["tenant_id"], unique=False)
    op.create_index("ix_contact_jobs_tipo", "contact_jobs", ["tipo"], unique=False)
    op.create_index("ix_contact_jobs_status", "contact_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_contact_jobs_status", table_name="contact_jobs")
    op.drop_index("ix_contact_jobs_tipo", table_name="contact_jobs")
    op.drop_index("ix_contact_jobs_tenant_id", table_name="contact_jobs")
    op.drop_table("contact_jobs")
