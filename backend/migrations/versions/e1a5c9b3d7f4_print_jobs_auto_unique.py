"""print_jobs: índice único parcial do auto-print (F10.7)

A idempotência do auto-print era só um "já existe job deste pedido?" checado em
Python antes do INSERT — com BACKEND_WORKERS=2 (default em prod) dois eventos
concorrentes do mesmo pedido atravessam a checagem e criam dois cupons.

O índice é PARCIAL (`requested_by = 'auto_print'`) de propósito: impressão
manual do operador e reimpressão continuam podendo gerar quantos jobs quiserem.
Quem perde a corrida recebe IntegrityError e o `enqueue` devolve o job do
vencedor.

Revision ID: e1a5c9b3d7f4
Revises: d7e4b1a9c6f2
Create Date: 2026-09-20
"""

from alembic import op
import sqlalchemy as sa
from typing import Union


revision: str = "e1a5c9b3d7f4"
down_revision: Union[str, None] = "d7e4b1a9c6f2"
branch_labels = None
depends_on = None

_AUTO_PRINT_ONLY = sa.text("requested_by = 'auto_print'")


def upgrade() -> None:
    op.create_index(
        "uq_print_jobs_auto_order",
        "print_jobs",
        ["tenant_id", "order_id"],
        unique=True,
        sqlite_where=_AUTO_PRINT_ONLY,
        postgresql_where=_AUTO_PRINT_ONLY,
    )


def downgrade() -> None:
    op.drop_index("uq_print_jobs_auto_order", table_name="print_jobs")
