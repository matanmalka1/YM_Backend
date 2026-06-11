"""add updated_at to correspondence_entries

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-11

Adds a nullable updated_at column to correspondence_entries. Correspondence
is mutable via PATCH (the previous "immutable" docstring was stale). Existing
rows stay NULL (no backfill — creation is not an update). Populated at runtime
via the model's onupdate=utcnow_aware on real updates. See docs/api-todo.md #46.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "correspondence_entries",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("correspondence_entries", "updated_at")
