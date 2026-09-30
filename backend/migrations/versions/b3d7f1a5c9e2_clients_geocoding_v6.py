"""clients: cidade/uf/nome_importado (geocoding de contatos .vcf)

Revision ID: b3d7f1a5c9e2
Revises: a9c4e1b7d2f5
Create Date: 2026-09-25

Fase 2 (§7) do renomeador automático de contatos — parte aditiva em `clients`:
- cidade/uf: o ViaCEP por endereço exige município (o parser também preenche
  pelo ADR/geocoding);
- nome_importado: preserva o nome BRUTO da importação (com o código legado)
  para rastreabilidade — `nome` passa a ser só nome de pessoa (§8.3).

**Escopo deliberado:** as tabelas `geocode_cache` e `contact_jobs` do §7 NÃO
entram aqui. O guard de integridade (`tests/integrity_audit.py`, checagem
`dado-invisivel`) exige consumidor fora da camada de modelos, e o scan ignora
`app/infrastructure/repositories/**` — logo uma tabela nova precisa do serviço/
router que a usa na MESMA mudança. Elas entram nos PRs que as consomem
(geocode_cache na etapa de geocoding; contact_jobs na etapa do job em lote).

Aditiva: nenhum default muda o comportamento atual. Bancos legados SQLite
recebem as colunas pelo _ensure_sqlite_columns() do init_db; esta migration é
a via versionada do PostgreSQL.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3d7f1a5c9e2"
down_revision: Union[str, None] = "a9c4e1b7d2f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("cidade", sa.String(), nullable=True))
    op.add_column("clients", sa.Column("uf", sa.String(), nullable=True))
    op.add_column("clients", sa.Column("nome_importado", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "nome_importado")
    op.drop_column("clients", "uf")
    op.drop_column("clients", "cidade")
