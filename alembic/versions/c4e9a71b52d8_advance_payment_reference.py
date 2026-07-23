"""advance payment reference

Adds ``advance_payments.payment_reference`` — the bank/authority reference
(אסמכתה) of the single payment recorded on the period, as reported by the
client. Nullable free text; no index (looked up per record, not searched).

Revision ID: c4e9a71b52d8
Revises: 8f1039f41468
Create Date: 2026-07-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e9a71b52d8"
down_revision: str | Sequence[str] | None = "8f1039f41468"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "advance_payments",
        sa.Column("payment_reference", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("advance_payments", "payment_reference")
