"""refund cash amount

Revision ID: 8b1d3c5e7a90
Revises: 46ffe0176ef4
Create Date: 2026-10-16 10:00:00.000000

Records how much of each refund went back as cash, so card / KHQR refunds no longer
reduce the expected cash in the drawer. Existing refunds are filled in from their sale's payments.
"""
from collections import defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b1d3c5e7a90'
down_revision: Union[str, Sequence[str], None] = '46ffe0176ef4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _div_round(numerator: int, denominator: int) -> int:
    return (2 * numerator + denominator) // (2 * denominator)


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('refunds', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cash_amount', sa.Integer(), nullable=False, server_default='0'))

    bind = op.get_bind()
    sales = {row.id: row for row in bind.execute(sa.text("SELECT id, total, change_due FROM sales WHERE refunded_total > 0"))}
    cash = defaultdict(int)
    for row in bind.execute(sa.text("SELECT sale_id, amount_usd FROM payments WHERE method = 'cash'")):
        if row.sale_id in sales:
            cash[row.sale_id] += row.amount_usd
    refunded = defaultdict(int)
    for row in bind.execute(sa.text("SELECT id, sale_id, amount FROM refunds ORDER BY id")):
        sale = sales.get(row.sale_id)
        if sale is None or sale.total <= 0:
            continue
        sale_cash = min(max(cash[row.sale_id] - sale.change_due, 0), sale.total)
        before = refunded[row.sale_id]
        refunded[row.sale_id] += row.amount
        part = _div_round(refunded[row.sale_id] * sale_cash, sale.total) - _div_round(before * sale_cash, sale.total)
        if part:
            bind.execute(sa.text("UPDATE refunds SET cash_amount = :part WHERE id = :id"), {"part": part, "id": row.id})


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('refunds', schema=None) as batch_op:
        batch_op.drop_column('cash_amount')
