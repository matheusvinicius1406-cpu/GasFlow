"""P0 multiempresa: unicidade de conversa WhatsApp por tenant

Revision ID: c1a2b3d4e5f6
Revises: 9f4b7e2a6c31
Create Date: 2026-10-10

Conversas de WhatsApp eram únicas por (account_id, phone_number) global —
duas empresas do mesmo ambiente não podiam ter conversa com o mesmo
telefone, e o serviço escrevia sempre como tenant "default".

- Backfill: linhas existentes viram tenant 'default' (comportamento de
  produção preservado: o serviço Node continua gravando como default).
- Unique constraint trocada para (tenant_id, account_id, phone_number);
  a coluna tenant_id e o índice ix_whatsapp_conversations_tenant_id já
  existiam no baseline.

SQLite: troca de constraint exige batch_alter_table (recriação da tabela,
mesmo padrão do audit 2026-09).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c1a2b3d4e5f6"
down_revision: Union[str, None] = "9f4b7e2a6c31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Backfill: toda conversa pré-multiempresa pertence ao tenant default.
    op.execute("UPDATE whatsapp_conversations SET tenant_id = 'default' WHERE tenant_id IS NULL")

    # 2. Unicidade passa a ser por tenant (SQLite: recriação via batch).
    with op.batch_alter_table("whatsapp_conversations", schema=None) as batch_op:
        batch_op.drop_constraint("uq_wa_conversation_account_phone", type_="unique")
        batch_op.create_unique_constraint(
            "uq_wa_conversation_tenant_account_phone",
            ["tenant_id", "account_id", "phone_number"],
        )


def downgrade() -> None:
    # Volta a unicidade global. Linhas de tenants diferentes com o mesmo
    # (account_id, phone_number) fariam o downgrade falhar — nesse caso
    # é preciso tratar os dados antes (fora do escopo do downgrade).
    with op.batch_alter_table("whatsapp_conversations", schema=None) as batch_op:
        batch_op.drop_constraint("uq_wa_conversation_tenant_account_phone", type_="unique")
        batch_op.create_unique_constraint(
            "uq_wa_conversation_account_phone",
            ["account_id", "phone_number"],
        )
