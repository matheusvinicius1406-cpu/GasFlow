"""coupons: referral (F4) — invite_token/is_referral em coupons + tabela referrals

Revision ID: b7d3e9f2a4c8
Revises: e9b2c4d6a1f3
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa
from typing import Union


revision: str = "b7d3e9f2a4c8"
down_revision: Union[str, None] = "e9b2c4d6a1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("coupons", sa.Column("invite_token", sa.String(length=64), nullable=True))
    op.add_column("coupons", sa.Column("is_referral", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_coupons_invite_token", "coupons", ["invite_token"], unique=True)

    op.create_table(
        "referrals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="default"),
        sa.Column("invite_token", sa.String(length=64), nullable=False),
        sa.Column("referrer_client_codigo", sa.String(length=20), nullable=False),
        sa.Column("referred_client_codigo", sa.String(length=20), nullable=True),
        sa.Column("referrer_coupon_id", sa.String(length=36), nullable=True),
        sa.Column("referred_coupon_id", sa.String(length=36), nullable=True),
        sa.Column("referred_name", sa.String(length=100), nullable=True),
        sa.Column("referred_phone", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "invite_token", name="uq_referral_tenant_token"),
    )
    op.create_index("ix_referrals_invite_token", "referrals", ["invite_token"])
    op.create_index("ix_referrals_referrer_client_codigo", "referrals", ["referrer_client_codigo"])
    op.create_index("ix_referrals_referred_client_codigo", "referrals", ["referred_client_codigo"])


def downgrade() -> None:
    op.drop_index("ix_referrals_referred_client_codigo", table_name="referrals")
    op.drop_index("ix_referrals_referrer_client_codigo", table_name="referrals")
    op.drop_index("ix_referrals_invite_token", table_name="referrals")
    op.drop_table("referrals")
    op.drop_index("ix_coupons_invite_token", table_name="coupons")
    op.drop_column("coupons", "is_referral")
    op.drop_column("coupons", "invite_token")
