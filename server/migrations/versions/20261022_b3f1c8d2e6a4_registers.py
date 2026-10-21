"""registers

Revision ID: b3f1c8d2e6a4
Revises: e4b8c2a91d07
Create Date: 2026-10-22 09:00:00.000000

Registers (tills / counters, each with its own cash drawer); a shift opens on one. Every shop starts with
"Counter 1" and past shifts go on it; shifts open right now get a counter each (one open shift per drawer).
"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f1c8d2e6a4'
down_revision: Union[str, Sequence[str], None] = 'e4b8c2a91d07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    registers = op.create_table('registers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    with op.batch_alter_table('shifts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('register_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_shifts_register_id'), ['register_id'], unique=False)
        batch_op.create_foreign_key('fk_shifts_register_id', 'registers', ['register_id'], ['id'])

    conn = op.get_bind()
    open_now = [row[0] for row in conn.execute(sa.text('SELECT id FROM shifts WHERE closed_at IS NULL ORDER BY id'))]
    made = datetime.now().replace(microsecond=0)
    op.bulk_insert(registers, [{'id': n, 'name': f'Counter {n}', 'is_active': True, 'created_at': made}
                               for n in range(1, max(len(open_now), 1) + 1)])
    op.execute('UPDATE shifts SET register_id = 1')
    for n, shift_id in enumerate(open_now[1:], start=2):
        conn.execute(sa.text('UPDATE shifts SET register_id = :n WHERE id = :id'), {'n': n, 'id': shift_id})


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('shifts', schema=None) as batch_op:
        batch_op.drop_constraint('fk_shifts_register_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_shifts_register_id'))
        batch_op.drop_column('register_id')

    op.drop_table('registers')
