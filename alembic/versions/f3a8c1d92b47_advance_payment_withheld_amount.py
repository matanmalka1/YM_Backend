"""advance payment withheld amount

Adds ``advance_payments.withheld_amount`` — the withheld-at-source credit
(ניכוי במקור) subtracted from ``calculated_amount`` to derive
``expected_amount``. Nullable; NULL means "none entered", treated as zero.

Revision ID: f3a8c1d92b47
Revises: c4e9a71b52d8
Create Date: 2026-07-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a8c1d92b47"
down_revision: str | Sequence[str] | None = "c4e9a71b52d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "advance_payments",
        sa.Column("withheld_amount", sa.Numeric(precision=12, scale=2), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("advance_payments", "withheld_amount")
