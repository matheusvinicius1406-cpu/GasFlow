"""clients: campos de geocoding do renomeador de contatos (.vcf)

Revision ID: a9c4e1b7d2f5
Revises: c4e8a2f6b1d7
Create Date: 2026-09-25

ADR-0001 — renomeador automático de contatos (.vcf):
- cep: CEP do contato (best-effort, via Nominatim/postcode);
- entre_ruas: ruas vizinhas resolvidas ("Rua A e Rua B"), opcional;
- geocode_status: OK | NAO_ENCONTRADO | PENDENTE (triagem, nunca perde contato);
- lat/lng: coordenadas resolvidas (reuso do GeoPoint do domínio).

Aditivas e nullable — nenhum default quebra o comportamento atual. Bancos
legados SQLite recebem as MESMAS colunas pelo _ensure_sqlite_columns() do
init_db (create_all não altera tabela existente); aqui fica a via versionada
do PostgreSQL.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9c4e1b7d2f5"
down_revision: Union[str, None] = "c4e8a2f6b1d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("cep", sa.String(9), nullable=True))
    op.add_column("clients", sa.Column("entre_ruas", sa.String(), nullable=True))
    op.add_column("clients", sa.Column("geocode_status", sa.String(20), nullable=True))
    op.add_column("clients", sa.Column("lat", sa.Float(), nullable=True))
    op.add_column("clients", sa.Column("lng", sa.Float(), nullable=True))
    op.create_index("ix_clients_geocode_status", "clients", ["geocode_status"])


def downgrade() -> None:
    op.drop_index("ix_clients_geocode_status", table_name="clients")
    op.drop_column("clients", "lng")
    op.drop_column("clients", "lat")
    op.drop_column("clients", "geocode_status")
    op.drop_column("clients", "entre_ruas")
    op.drop_column("clients", "cep")
