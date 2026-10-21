"""held orders stay at their outlet

Revision ID: a8e4f1c6b2d9
Revises: c5d2a7e9f310
Create Date: 2026-10-24 09:00:00.000000

A held order belongs to the outlet where the customer waits: only that outlet's tills see and finish it.
Orders held so far stay with the main shop.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8e4f1c6b2d9'
down_revision: Union[str, Sequence[str], None] = 'c5d2a7e9f310'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('parked_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('location_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_parked_orders_location_id', 'locations', ['location_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('parked_orders', schema=None) as batch_op:
        batch_op.drop_constraint('fk_parked_orders_location_id', type_='foreignkey')
        batch_op.drop_column('location_id')
