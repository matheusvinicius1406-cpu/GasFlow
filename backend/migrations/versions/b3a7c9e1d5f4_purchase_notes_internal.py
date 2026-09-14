"""purchase notes: notas de compra internas (sem SEFAZ)

Revision ID: b3a7c9e1d5f4
Revises: f2b9d4c6a8e0
Create Date: 2026-09-14

Item 2 — Notas de Compra: documento interno de compra do fornecedor de
gás (ex.: "Marcos Gás, CNPJ ..., compra do dia ..."). Não é NF-e e não
tem valor fiscal. Confirmação dá entrada no estoque (ENTRY idempotente).
Aditivo; usa batch_alter_table (SQLite).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3a7c9e1d5f4"
down_revision: Union[str, None] = "f2b9d4c6a8e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "purchase_notes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, server_default="default"),
        sa.Column("note_number", sa.Integer(), nullable=False),
        sa.Column("supplier_name", sa.String(length=200), nullable=False),
        sa.Column("supplier_cnpj", sa.String(length=18), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("observations", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("pdf_path", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tenant_id", "note_number", name="uq_purchase_notes_tenant_number"),
    )
    op.create_index("idx_purchase_notes_tenant_status", "purchase_notes", ["tenant_id", "status"])
    op.create_index("idx_purchase_notes_supplier", "purchase_notes", ["supplier_name"])

    op.create_table(
        "purchase_note_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "purchase_note_id",
            sa.String(length=36),
            sa.ForeignKey("purchase_notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_codigo", sa.String(length=50), nullable=False),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("subtotal_cents", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_index("idx_purchase_note_items_note", "purchase_note_items", ["purchase_note_id"])


def downgrade() -> None:
    op.drop_index("idx_purchase_note_items_note", table_name="purchase_note_items")
    op.drop_table("purchase_note_items")
    op.drop_index("idx_purchase_notes_supplier", table_name="purchase_notes")
    op.drop_index("idx_purchase_notes_tenant_status", table_name="purchase_notes")
    op.drop_table("purchase_notes")
