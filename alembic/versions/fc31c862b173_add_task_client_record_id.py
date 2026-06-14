"""add task client record id

Revision ID: fc31c862b173
Revises: 3724bd314d54
Create Date: 2026-06-14 22:41:39.047325

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fc31c862b173'
down_revision: Union[str, Sequence[str], None] = '3724bd314d54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    FK constraint and op.drop_constraint in downgrade() are PostgreSQL-only —
    SQLite cannot add/drop FK constraints after table creation. Tests use
    in-memory SQLite with Base.metadata.create_all() (bypasses Alembic entirely),
    so this migration only ever runs on PostgreSQL in practice.
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.add_column('tasks', sa.Column('client_record_id', sa.Integer(), nullable=True))
    op.create_index('idx_tasks_client_record_id', 'tasks', ['client_record_id'], unique=False)
    if is_postgres:
        op.create_foreign_key(
            'tasks_client_record_id_fkey',
            'tasks', 'client_records',
            ['client_record_id'], ['id'],
        )

    # Backfill client_record_id from source records.
    # Tasks with source_domain='task', unsupported domains, or whose source row
    # is soft-deleted remain client_record_id=NULL by design (global/unresolvable).
    if is_postgres:
        op.execute("""
            UPDATE tasks t SET client_record_id = v.client_record_id
            FROM vat_work_items v
            WHERE t.source_domain = 'vat_work_item' AND t.source_id = v.id
              AND t.client_record_id IS NULL AND v.deleted_at IS NULL
        """)
        op.execute("""
            UPDATE tasks t SET client_record_id = a.client_record_id
            FROM annual_reports a
            WHERE t.source_domain = 'annual_report' AND t.source_id = a.id
              AND t.client_record_id IS NULL AND a.deleted_at IS NULL
        """)
        op.execute("""
            UPDATE tasks t SET client_record_id = ap.client_record_id
            FROM advance_payments ap
            WHERE t.source_domain = 'advance_payment' AND t.source_id = ap.id
              AND t.client_record_id IS NULL AND ap.deleted_at IS NULL
        """)
        op.execute("""
            UPDATE tasks t SET client_record_id = c.client_record_id
            FROM charges c
            WHERE t.source_domain = 'charge' AND t.source_id = c.id
              AND t.client_record_id IS NULL AND c.deleted_at IS NULL
        """)
        op.execute("""
            UPDATE tasks t SET client_record_id = b.client_record_id
            FROM binders b
            WHERE t.source_domain = 'binder' AND t.source_id = b.id
              AND t.client_record_id IS NULL AND b.deleted_at IS NULL
        """)
    else:
        # SQLite: correlated subquery UPDATE (FK DDL already skipped above)
        for domain, table in [
            ("vat_work_item", "vat_work_items"),
            ("annual_report", "annual_reports"),
            ("advance_payment", "advance_payments"),
            ("charge", "charges"),
            ("binder", "binders"),
        ]:
            op.execute(f"""
                UPDATE tasks SET client_record_id = (
                    SELECT client_record_id FROM {table}
                    WHERE {table}.id = tasks.source_id AND {table}.deleted_at IS NULL
                )
                WHERE source_domain = '{domain}' AND client_record_id IS NULL
            """)


def downgrade() -> None:
    """Downgrade schema. FK drop is PostgreSQL-only (see upgrade docstring)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint('tasks_client_record_id_fkey', 'tasks', type_='foreignkey')
    op.drop_index('idx_tasks_client_record_id', table_name='tasks')
    op.drop_column('tasks', 'client_record_id')
