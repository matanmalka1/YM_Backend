"""add updated_at to binders

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-11

Adds a nullable updated_at column to binders. Existing rows stay NULL
(no backfill — creation is not an update). Populated at runtime via the
model's onupdate=utcnow on real mutations (status/handover/capacity/
soft-delete). See docs/api-todo.md #46.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("binders", sa.Column("updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("binders", "updated_at")
