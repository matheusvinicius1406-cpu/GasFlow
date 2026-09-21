"""operator JWT: refresh rotativo e escopo de plataforma na sessão

Revision ID: a4c8e2f6b1d3
Revises: e1a5c9b3d7f4
Create Date: 2026-09-21

O operador passa a receber **access JWT de vida curta + refresh rotativo**. A
linha em `auth_sessions` continua sendo a fonte de verdade da revogação, e é
também a **família** do refresh token:

- `refresh_token_hash`: sha256 do refresh corrente (o token em claro nunca é
  gravado);
- `refresh_prev_hash`: hash do refresh anterior, existindo só para detectar
  **reuso** de token já rotacionado → a sessão inteira é revogada, igual ao
  fluxo mobile (`driver_refresh_tokens`);
- `refresh_expires_at`: vida do refresh (7 dias), independente do access
  (15 min);
- `refresh_rotated_at`: quando houve a última rotação;
- `platform`: escopo do par de tokens (`desktop`/`mobile`) — é o que permite
  sessão simultânea desktop+mobile sem uma derrubar a outra.

Por que na sessão e não numa tabela nova: revogar sessão já revoga acesso
(`validate_token` lê a linha), `MAX_SESSIONS_PER_USER` já conta linhas daqui e
o `last_seen_at` já é atualizado aqui. Uma tabela paralela duplicaria essas
três responsabilidades.

SQLite: todas as alterações via batch_alter_table.
"""

from alembic import op
import sqlalchemy as sa

revision = "a4c8e2f6b1d3"
down_revision = "e1a5c9b3d7f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("auth_sessions") as batch:
        batch.add_column(sa.Column("refresh_token_hash", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("refresh_prev_hash", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("refresh_expires_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("refresh_rotated_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("platform", sa.String(length=20), nullable=True))
        batch.create_index("ix_auth_session_refresh_hash", ["refresh_token_hash"])


def downgrade() -> None:
    with op.batch_alter_table("auth_sessions") as batch:
        batch.drop_index("ix_auth_session_refresh_hash")
        batch.drop_column("platform")
        batch.drop_column("refresh_rotated_at")
        batch.drop_column("refresh_expires_at")
        batch.drop_column("refresh_prev_hash")
        batch.drop_column("refresh_token_hash")
