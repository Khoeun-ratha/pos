"""expenses

Revision ID: e4b8c2a91d07
Revises: d7a3e91f2b40
Create Date: 2026-10-21 09:00:00.000000

Shop expenses (rent, electricity, salaries...), optionally paid from the cash drawer.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4b8c2a91d07'
down_revision: Union[str, Sequence[str], None] = 'd7a3e91f2b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('expenses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('spent_on', sa.Date(), nullable=False),
    sa.Column('category', sa.String(length=50), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('note', sa.String(length=200), nullable=True),
    sa.Column('cash_movement_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['cash_movement_id'], ['cash_movements.id'], name='fk_expenses_cash_movement_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_expenses_user_id'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_expenses_spent_on'), ['spent_on'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_expenses_spent_on'))

    op.drop_table('expenses')
