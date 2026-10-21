"""branch outlets

Revision ID: c5d2a7e9f310
Revises: b3f1c8d2e6a4
Create Date: 2026-10-23 09:00:00.000000

Branches sell: a register stands in the main shop or a branch, a sale records the outlet that sold it (and whose
stock it took), and a user may have a home branch. Everything so far stays as it was: the main shop (no location).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5d2a7e9f310'
down_revision: Union[str, Sequence[str], None] = 'b3f1c8d2e6a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('registers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('location_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_registers_location_id', 'locations', ['location_id'], ['id'])

    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.add_column(sa.Column('location_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_sales_location_id'), ['location_id'], unique=False)
        batch_op.create_foreign_key('fk_sales_location_id', 'locations', ['location_id'], ['id'])

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('location_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_users_location_id', 'locations', ['location_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_users_location_id', type_='foreignkey')
        batch_op.drop_column('location_id')

    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.drop_constraint('fk_sales_location_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_sales_location_id'))
        batch_op.drop_column('location_id')

    with op.batch_alter_table('registers', schema=None) as batch_op:
        batch_op.drop_constraint('fk_registers_location_id', type_='foreignkey')
        batch_op.drop_column('location_id')
