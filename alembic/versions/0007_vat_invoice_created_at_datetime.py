"""convert vat invoice created_at to datetime

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-13

VatInvoice.created_at is a system timestamp, not a VAT document date. Existing
date-only values have no recoverable time component, so PostgreSQL preserves
them as midnight timestamps during the type conversion.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "vat_invoices",
        "created_at",
        existing_type=sa.Date(),
        type_=sa.DateTime(),
        existing_nullable=False,
        postgresql_using="created_at::timestamp",
    )


def downgrade() -> None:
    op.alter_column(
        "vat_invoices",
        "created_at",
        existing_type=sa.DateTime(),
        type_=sa.Date(),
        existing_nullable=False,
        postgresql_using="created_at::date",
    )
