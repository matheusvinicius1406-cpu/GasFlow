"""products: campos de pagamento no cartão (reorg v4)

Revision ID: e9b2c4d6a1f3
Revises: c5e8a1f4b7d2
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa
from typing import Union


revision: str = "e9b2c4d6a1f3"
down_revision: Union[str, None] = "c5e8a1f4b7d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("cartao_habilitado", sa.Boolean(), nullable=True))
    op.add_column("products", sa.Column("preco_cartao_1x", sa.Float(), nullable=True))
    op.add_column("products", sa.Column("preco_cartao_2x", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "preco_cartao_2x")
    op.drop_column("products", "preco_cartao_1x")
    op.drop_column("products", "cartao_habilitado")
