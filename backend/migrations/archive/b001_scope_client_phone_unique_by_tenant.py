"""scope client phone unique by tenant

Revision ID: b001
Revises: a074610b4bbb
Create Date: 2026-08-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b001'
down_revision: Union[str, Sequence[str], None] = 'a074610b4bbb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Scope client phone uniqueness by tenant.

    Changes:
    - Drop global UNIQUE(telefone) constraint
    - Add UNIQUE(tenant_id, telefone) constraint
    - Keep existing index ix_clients_telefone for search performance
    """
    # Step 1: Drop the global unique constraint on telefone
    op.drop_constraint('uq_clients_telefone', 'clients', type_='unique')

    # Step 2: Add the per-tenant unique constraint
    op.create_unique_constraint(
        'uq_client_tenant_telefone',
        'clients',
        ['tenant_id', 'telefone']
    )


def downgrade() -> None:
    """Revert to global phone uniqueness."""
    op.drop_constraint('uq_client_tenant_telefone', 'clients', type_='unique')
    op.create_unique_constraint('uq_clients_telefone', 'clients', ['telefone'])
