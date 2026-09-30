"""geocode_cache: cache de geocoding por rua (Fase 2 §6 / ADR-0004)

Revision ID: d4e8b2c6f1a3
Revises: b3d7f1a5c9e2
Create Date: 2026-09-25

Cache global (sem tenant_id — dado público do OSM) com a chave = sha256 de
`rua|bairro|cidade|uf`. Uma linha por RUA, não por endereço: 10.000 contatos em
~50 ruas custam ~50 requisições ao provedor (ADR-0004).

`intersecoes` (JSON) entra já na v7 mesmo que quem a preencha seja o Overpass na
etapa 6 — sem a coluna, o cache já gravado ficaria sem espaço para o dado e a
etapa 6 exigiria outra migration.

Aditiva: só cria tabela nova, não toca em `clients` nem em nada existente.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e8b2c6f1a3"
down_revision: Union[str, None] = "b3d7f1a5c9e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "geocode_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chave", sa.String(length=64), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("rua", sa.String(), nullable=True),
        sa.Column("bairro", sa.String(), nullable=True),
        sa.Column("cidade", sa.String(), nullable=True),
        sa.Column("uf", sa.String(length=2), nullable=True),
        sa.Column("cep", sa.String(length=9), nullable=True),
        sa.Column("provider", sa.String(length=20), nullable=True),
        sa.Column("intersecoes", sa.JSON(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_geocode_cache_id", "geocode_cache", ["id"], unique=False)
    op.create_index("ix_geocode_cache_chave", "geocode_cache", ["chave"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_geocode_cache_chave", table_name="geocode_cache")
    op.drop_index("ix_geocode_cache_id", table_name="geocode_cache")
    op.drop_table("geocode_cache")
