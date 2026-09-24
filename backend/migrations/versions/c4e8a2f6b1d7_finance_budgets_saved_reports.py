"""finance: orçamento mensal + relatórios salvos (Central Financeira P3)

Revision ID: c4e8a2f6b1d7
Revises: f3a9c1e7d204
Create Date: 2026-09-24

P3 — tabelas novas da Central Financeira:
- finance_budgets: orçamento mensal por categoria (V4: tenant+ano+mês+categoria);
- finance_saved_reports: relatórios filtrados salvos pelo usuário.

Aditivas. Bancos legados `create_all` recebem as mesmas tabelas pelo
init_db() (create_all cria tabelas novas), e a cadeia versionada passa a
ser gerenciada por esta migration a partir de f3a9c1e7d204.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8a2f6b1d7"
down_revision: Union[str, None] = "f3a9c1e7d204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "finance_budgets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "year", "month", "category", name="uq_finance_budgets_period"),
    )
    op.create_index("ix_finance_budgets_tenant_id", "finance_budgets", ["tenant_id"])
    op.create_index("ix_finance_budgets_id", "finance_budgets", ["id"])
    op.create_index("ix_finance_budgets_period", "finance_budgets", ["year", "month"])

    op.create_table(
        "finance_saved_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("report_type", sa.String(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_finance_saved_reports_name"),
    )
    op.create_index("ix_finance_saved_reports_tenant_id", "finance_saved_reports", ["tenant_id"])
    op.create_index("ix_finance_saved_reports_id", "finance_saved_reports", ["id"])
    op.create_index("ix_finance_saved_reports_created", "finance_saved_reports", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_finance_saved_reports_created", table_name="finance_saved_reports")
    op.drop_index("ix_finance_saved_reports_id", table_name="finance_saved_reports")
    op.drop_index("ix_finance_saved_reports_tenant_id", table_name="finance_saved_reports")
    op.drop_table("finance_saved_reports")
    op.drop_index("ix_finance_budgets_period", table_name="finance_budgets")
    op.drop_index("ix_finance_budgets_id", table_name="finance_budgets")
    op.drop_index("ix_finance_budgets_tenant_id", table_name="finance_budgets")
    op.drop_table("finance_budgets")
