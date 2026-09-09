"""settings, coupons, redemptions e site_leads (43 tabelas)

Revision ID: a7c1e9f2b4d6
Revises: 12f8390d5be4
Create Date: 2026-09-06

Nova revision (não autogerada) — espelha exatamente os models:
- system_settings (SystemSettingModel)
- coupons / coupon_redemptions (CouponModel / CouponRedemptionModel)
- site_leads (LeadModel)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c1e9f2b4d6"
down_revision: Union[str, None] = "12f8390d5be4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_editable", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("system_settings", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_system_settings_category"), ["category"], unique=False)

    op.create_table(
        "coupons",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("value", sa.Numeric(10, 2), nullable=True),
        sa.Column("min_order_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("max_discount", sa.Numeric(10, 2), nullable=True),
        sa.Column("applicable_products", sa.JSON(), nullable=True),
        sa.Column("applicable_customers", sa.JSON(), nullable=True),
        sa.Column("start_date", sa.DateTime(), nullable=False),
        sa.Column("end_date", sa.DateTime(), nullable=False),
        sa.Column("usage_limit", sa.Integer(), nullable=False),
        sa.Column("usage_per_customer", sa.Integer(), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_coupon_tenant_code"),
    )
    with op.batch_alter_table("coupons", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_coupons_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_coupons_code"), ["code"], unique=False)

    op.create_table(
        "coupon_redemptions",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("coupon_id", sa.String(length=36), nullable=False),
        sa.Column("order_codigo", sa.String(), nullable=False),
        sa.Column("client_codigo", sa.String(), nullable=True),
        sa.Column("discount_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("fee_saved", sa.Numeric(10, 2), nullable=False),
        sa.Column("delivery_fee_before", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "order_codigo", name="uq_coupon_redemption_order"),
    )
    with op.batch_alter_table("coupon_redemptions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_coupon_redemptions_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_coupon_redemptions_coupon_id"), ["coupon_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_coupon_redemptions_order_codigo"), ["order_codigo"], unique=False)

    op.create_table(
        "site_leads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("message", sa.String(length=2000), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("site_leads", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_site_leads_email"), ["email"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("site_leads", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_site_leads_email"))
    op.drop_table("site_leads")

    with op.batch_alter_table("coupon_redemptions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_coupon_redemptions_order_codigo"))
        batch_op.drop_index(batch_op.f("ix_coupon_redemptions_coupon_id"))
        batch_op.drop_index(batch_op.f("ix_coupon_redemptions_tenant_id"))
    op.drop_table("coupon_redemptions")

    with op.batch_alter_table("coupons", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_coupons_code"))
        batch_op.drop_index(batch_op.f("ix_coupons_tenant_id"))
    op.drop_table("coupons")

    with op.batch_alter_table("system_settings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_system_settings_category"))
    op.drop_table("system_settings")
