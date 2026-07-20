"""advance payment turnover provenance

Revision ID: 8a1c47d0b3e2
Revises: 2f2c4539ec3b
Create Date: 2026-07-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8a1c47d0b3e2'
down_revision: Union[str, Sequence[str], None] = '2f2c4539ec3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TURNOVER_SOURCE = postgresql.ENUM(
    'manual', 'vat_filed', 'vat_pending', name='turnoversource'
)


def upgrade() -> None:
    """Upgrade schema."""
    TURNOVER_SOURCE.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'advance_payments',
        sa.Column('turnover_source', TURNOVER_SOURCE, nullable=True),
    )
    op.add_column(
        'advance_payments',
        sa.Column('turnover_snapshot_at', sa.DateTime(), nullable=True),
    )
    # Existing rows carrying a turnover were all typed by an advisor: the VAT
    # snapshot command did not exist before this revision. Snapshot time is
    # unknowable retroactively and stays NULL.
    op.execute(
        "UPDATE advance_payments SET turnover_source = 'manual' "
        "WHERE turnover_amount IS NOT NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('advance_payments', 'turnover_snapshot_at')
    op.drop_column('advance_payments', 'turnover_source')
    # Postgres keeps the enum type after the column is dropped; drop it explicitly.
    TURNOVER_SOURCE.drop(op.get_bind(), checkfirst=True)
