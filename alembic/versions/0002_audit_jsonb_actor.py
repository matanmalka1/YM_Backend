"""phase 1a — audit JSONB + actor snapshot columns (additive)

Migrates entity_audit_logs / user_audit_logs to the two-model target shape:
- old_value/new_value (and user metadata_json) Text -> JSONB via explicit cast
- entity_audit_logs gains metadata_json (JSONB), actor_display_name, actor_type
  (NULLABLE with a temporary server_default="user"); performed_by becomes nullable
- user_audit_logs gains actor_display_name + target_display_name
- replaces the (entity_type, entity_id) index with performance composite indexes
  + the §8b expression index on (metadata_json->>'client_record_id', performed_at)

actor_type is enforced NOT NULL by the follow-up migration (0003_audit_actor_type_notnull) once writers
populate it. No legacy audit tables are touched.

Revision ID: 0002_audit_jsonb_actor
Revises: 3e2669e69e32
Create Date: 2026-06-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_audit_jsonb_actor"
down_revision: Union[str, Sequence[str], None] = "3e2669e69e32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── entity_audit_logs ────────────────────────────────────────────────────
    # Replace the (entity_type, entity_id) index with timestamp-aware composites.
    op.drop_index("idx_entity_audit_type_id", table_name="entity_audit_logs")

    op.alter_column(
        "entity_audit_logs",
        "old_value",
        existing_type=sa.Text(),
        type_=postgresql.JSONB(),
        existing_nullable=True,
        postgresql_using="old_value::jsonb",
    )
    op.alter_column(
        "entity_audit_logs",
        "new_value",
        existing_type=sa.Text(),
        type_=postgresql.JSONB(),
        existing_nullable=True,
        postgresql_using="new_value::jsonb",
    )
    op.add_column(
        "entity_audit_logs",
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "entity_audit_logs",
        sa.Column("actor_display_name", sa.String(), nullable=True),
    )
    # actor_type stays nullable here with a temp default so in-flight rows stay
    # valid; 0003 enforces NOT NULL and drops the default once writers populate it.
    op.add_column(
        "entity_audit_logs",
        sa.Column("actor_type", sa.String(), nullable=True, server_default="user"),
    )
    op.alter_column(
        "entity_audit_logs",
        "performed_by",
        existing_type=sa.Integer(),
        nullable=True,
    )

    op.create_index(
        "idx_entity_audit_entity_perf",
        "entity_audit_logs",
        ["entity_type", "entity_id", "performed_at"],
    )
    op.create_index(
        "idx_entity_audit_action_perf",
        "entity_audit_logs",
        ["action", "performed_at"],
    )
    op.create_index(
        "idx_entity_audit_performer_perf",
        "entity_audit_logs",
        ["performed_by", "performed_at"],
    )
    op.create_index(
        "idx_entity_audit_performed_at",
        "entity_audit_logs",
        ["performed_at"],
    )
    # §8b expression index for metadata_json->>'client_record_id' lookups.
    op.execute(
        "CREATE INDEX idx_entity_audit_client_ctx ON entity_audit_logs "
        "((metadata_json->>'client_record_id'), performed_at)"
    )

    # ── user_audit_logs ──────────────────────────────────────────────────────
    op.alter_column(
        "user_audit_logs",
        "metadata_json",
        existing_type=sa.Text(),
        type_=postgresql.JSONB(),
        existing_nullable=True,
        postgresql_using="metadata_json::jsonb",
    )
    op.add_column(
        "user_audit_logs",
        sa.Column("actor_display_name", sa.String(), nullable=True),
    )
    op.add_column(
        "user_audit_logs",
        sa.Column("target_display_name", sa.String(), nullable=True),
    )


def downgrade() -> None:
    # ── user_audit_logs ──────────────────────────────────────────────────────
    op.drop_column("user_audit_logs", "target_display_name")
    op.drop_column("user_audit_logs", "actor_display_name")
    op.alter_column(
        "user_audit_logs",
        "metadata_json",
        existing_type=postgresql.JSONB(),
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="metadata_json::text",
    )

    # ── entity_audit_logs ────────────────────────────────────────────────────
    op.execute("DROP INDEX IF EXISTS idx_entity_audit_client_ctx")
    op.drop_index("idx_entity_audit_performed_at", table_name="entity_audit_logs")
    op.drop_index("idx_entity_audit_performer_perf", table_name="entity_audit_logs")
    op.drop_index("idx_entity_audit_action_perf", table_name="entity_audit_logs")
    op.drop_index("idx_entity_audit_entity_perf", table_name="entity_audit_logs")

    # Fail-safe: performed_by NOT NULL cannot be restored if null-actor
    # (system/external_signer) rows exist. Refuse rather than destroy rows or
    # silently leave the column nullable.
    conn = op.get_bind()
    null_actor_rows = conn.execute(
        sa.text("SELECT COUNT(*) FROM entity_audit_logs WHERE performed_by IS NULL")
    ).scalar()
    if null_actor_rows:
        raise RuntimeError(
            "Cannot restore entity_audit_logs.performed_by NOT NULL: "
            f"{null_actor_rows} row(s) have NULL performed_by (system/external_signer "
            "actors). Downgrade refused — these rows would have to be deleted to "
            "restore the constraint. Resolve the null-actor rows first."
        )
    op.alter_column(
        "entity_audit_logs",
        "performed_by",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.drop_column("entity_audit_logs", "actor_type")
    op.drop_column("entity_audit_logs", "actor_display_name")
    op.drop_column("entity_audit_logs", "metadata_json")
    op.alter_column(
        "entity_audit_logs",
        "new_value",
        existing_type=postgresql.JSONB(),
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="new_value::text",
    )
    op.alter_column(
        "entity_audit_logs",
        "old_value",
        existing_type=postgresql.JSONB(),
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="old_value::text",
    )
    op.create_index(
        "idx_entity_audit_type_id",
        "entity_audit_logs",
        ["entity_type", "entity_id"],
    )
