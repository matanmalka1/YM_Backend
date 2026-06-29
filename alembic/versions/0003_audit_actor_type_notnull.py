"""phase 1b — enforce entity_audit_logs.actor_type NOT NULL

Runs after all EntityAuditLog writers populate actor_type (defaulting to "user").
Enforces NOT NULL and drops the temporary server_default added in 0002. New rows
must pass actor_type explicitly (the writer always does).

Downgrade restores the nullable column + temporary server_default="user" so the
0002 downgrade can then reverse the rest.

Revision ID: 0003_audit_actor_type_notnull
Revises: 0002_audit_jsonb_actor
Create Date: 2026-06-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_audit_actor_type_notnull"
down_revision: Union[str, Sequence[str], None] = "0002_audit_jsonb_actor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "entity_audit_logs",
        "actor_type",
        existing_type=sa.String(),
        nullable=False,
        server_default=None,
    )


def downgrade() -> None:
    op.alter_column(
        "entity_audit_logs",
        "actor_type",
        existing_type=sa.String(),
        nullable=True,
        server_default="user",
    )
