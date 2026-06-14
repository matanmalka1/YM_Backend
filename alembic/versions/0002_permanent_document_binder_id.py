"""permanent document binder id

Revision ID: c1a2b3d4e5f6
Revises: bfaed5b29bd3
Create Date: 2026-06-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'bfaed5b29bd3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('permanent_documents') as batch_op:
        batch_op.add_column(sa.Column('binder_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_permanent_documents_binder_id', 'binders', ['binder_id'], ['id']
        )
        batch_op.create_index(
            op.f('ix_permanent_documents_binder_id'), ['binder_id'], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('permanent_documents') as batch_op:
        batch_op.drop_index(op.f('ix_permanent_documents_binder_id'))
        batch_op.drop_constraint('fk_permanent_documents_binder_id', type_='foreignkey')
        batch_op.drop_column('binder_id')
