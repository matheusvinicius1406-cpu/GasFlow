"""ibge_fase3: CNEFE + Faces de Logradouro + origem das interseções (Fase 3)

Revision ID: 9f4b7e2a6c31
Revises: e5c9f3a7b1d2
Create Date: 2026-09-30

A Fase 3 troca o Overpass público por dado oficial do IBGE (Censo 2022) no
"entre ruas" (ADR-0008):

- ``cnefe_endereco``   — número ↔ coordenada (a âncora que o OSM não tem);
- ``logradouro_face``  — segmento entre dois nós (de onde sai o cruzamento);
- ``logradouro_no``    — nó arredondado, chave de coincidência de cruzamento;
- ``geocode_cache.intersecoes_provider`` — de onde veio a `intersecoes`
  (D23): a coluna nova é a única forma de a triagem separar ``ibge`` de
  ``overpass`` por linha — ``provider`` continua sendo o provedor do geocode.

Aditiva: só cria tabela e coluna nova, não altera dado existente. Não há
coluna geométrica: a junção é por chave inteira (setor|quadra|face), não por
espacial (por isso a Fase 3 não precisa de PostGIS).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9f4b7e2a6c31"
down_revision: Union[str, None] = "e5c9f3a7b1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cnefe_endereco",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cod_municipio", sa.String(length=7), nullable=False),
        sa.Column("cod_unico_endereco", sa.String(length=30), nullable=False),
        sa.Column("cod_setor", sa.String(length=20), nullable=False),
        sa.Column("num_quadra", sa.Integer(), nullable=True),
        sa.Column("num_face", sa.Integer(), nullable=True),
        sa.Column("num_endereco", sa.Integer(), nullable=True),
        sa.Column("chave_logradouro", sa.String(length=128), nullable=False),
        sa.Column("chave_nome", sa.String(length=128), nullable=False),
        sa.Column("nome_logradouro", sa.String(length=160), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("cep", sa.String(length=9), nullable=True),
        sa.Column("nv_geo_coord", sa.String(length=2), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cod_municipio", "cod_unico_endereco", name="uq_cnefe_endereco_chave"),
    )
    op.create_index("ix_cnefe_endereco_cod_municipio", "cnefe_endereco", ["cod_municipio"], unique=False)
    op.create_index(
        "ix_cnefe_endereco_municipio_logradouro", "cnefe_endereco", ["cod_municipio", "chave_logradouro"], unique=False
    )
    op.create_index("ix_cnefe_endereco_face", "cnefe_endereco", ["cod_setor", "num_quadra", "num_face"], unique=False)

    op.create_table(
        "logradouro_face",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cod_municipio", sa.String(length=7), nullable=False),
        sa.Column("cod_setor", sa.String(length=20), nullable=False),
        sa.Column("cod_quadra", sa.Integer(), nullable=True),
        sa.Column("cod_face", sa.Integer(), nullable=True),
        sa.Column("chave_logradouro", sa.String(length=128), nullable=False),
        sa.Column("nome_logradouro", sa.String(length=160), nullable=True),
        # Polilinha completa [[lat, lng], ...] (JSON): 22% das faces têm mais de
        # 2 pontos, então o par de extremidades sozinho perdia a forma.
        sa.Column("geom", sa.JSON(), nullable=True),
        sa.Column("tot_res", sa.Integer(), nullable=True),
        sa.Column("tot_geral", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_logradouro_face_cod_municipio", "logradouro_face", ["cod_municipio"], unique=False)
    op.create_index(
        "ix_logradouro_face_municipio_logradouro",
        "logradouro_face",
        ["cod_municipio", "chave_logradouro"],
        unique=False,
    )
    op.create_index("ix_logradouro_face_face", "logradouro_face", ["cod_setor", "cod_quadra", "cod_face"], unique=False)

    op.create_table(
        "logradouro_no",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cod_municipio", sa.String(length=7), nullable=False),
        sa.Column("node_lat", sa.Float(), nullable=False),
        sa.Column("node_lng", sa.Float(), nullable=False),
        sa.Column("chave_logradouro", sa.String(length=128), nullable=False),
        sa.Column("nome_logradouro", sa.String(length=160), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cod_municipio", "node_lat", "node_lng", "chave_logradouro", name="uq_logradouro_no"),
    )
    op.create_index("ix_logradouro_no_cod_municipio", "logradouro_no", ["cod_municipio"], unique=False)
    op.create_index(
        "ix_logradouro_no_municipio_logradouro", "logradouro_no", ["cod_municipio", "chave_logradouro"], unique=False
    )

    # Nullable: SQLite aceita ADD COLUMN sem default (mesmo padrão da v5).
    op.add_column("geocode_cache", sa.Column("intersecoes_provider", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("geocode_cache", "intersecoes_provider")

    op.drop_index("ix_logradouro_no_municipio_logradouro", table_name="logradouro_no")
    op.drop_index("ix_logradouro_no_cod_municipio", table_name="logradouro_no")
    op.drop_table("logradouro_no")

    op.drop_index("ix_logradouro_face_face", table_name="logradouro_face")
    op.drop_index("ix_logradouro_face_municipio_logradouro", table_name="logradouro_face")
    op.drop_index("ix_logradouro_face_cod_municipio", table_name="logradouro_face")
    op.drop_table("logradouro_face")

    op.drop_index("ix_cnefe_endereco_face", table_name="cnefe_endereco")
    op.drop_index("ix_cnefe_endereco_municipio_logradouro", table_name="cnefe_endereco")
    op.drop_index("ix_cnefe_endereco_cod_municipio", table_name="cnefe_endereco")
    op.drop_table("cnefe_endereco")
