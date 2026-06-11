"""add updated_at to signature_requests

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-11

Adds a nullable updated_at column to signature_requests. Existing rows
stay NULL (no backfill — creation is not an update). Populated at runtime
via the model's onupdate=utcnow on real mutations (send/sign/decline/
cancel/expire/soft-delete). The append-only SignatureAuditEvent table is
unchanged. See docs/api-todo.md #46.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "signature_requests", sa.Column("updated_at", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("signature_requests", "updated_at")
