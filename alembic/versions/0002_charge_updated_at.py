"""add updated_at to charges

Revision ID: 0002
Revises: bfaed5b29bd3
Create Date: 2026-06-11

Adds a nullable updated_at column to charges. Existing rows stay NULL
(no backfill from created_at — creation is not an update). The column is
populated at runtime via the model's onupdate=utcnow on real mutations
(issue / pay / cancel / soft-delete). See docs/api-todo.md #46.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "bfaed5b29bd3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("charges", sa.Column("updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("charges", "updated_at")
