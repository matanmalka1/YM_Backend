"""
EntityAuditLog — generic, append-only audit trail for domain mutations.

Design decisions:
- entity_type is String (not enum) — expands freely without migrations.
  Use ENTITY_* constants from app/audit/audit_constants.py.
- action is String — use ACTION_* constants, never raw strings in service code.
- old_value / new_value are JSON snapshots of the changed fields only (not full rows).
  Stored as JSONB on PostgreSQL (JSON on SQLite) — the writer persists dict/list
  objects directly, no json.dumps wrapping.
- actor_type records the kind of actor (user | system | external_signer);
  actor_display_name is an immutable snapshot of the actor name at write time so
  later user renames never rewrite historical audit display.
- performed_by is nullable: system/external_signer rows carry no users.id FK.
- NO soft delete — audit logs are immutable by design.
  Corrections are made by appending new entries, never deleting old ones.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.time_utils import utcnow


class EntityAuditLog(Base):
    __tablename__ = "entity_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(nullable=False, index=True)
    performed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # user | system | external_signer — see app/audit/audit_constants.py
    actor_type: Mapped[str] = mapped_column(String, nullable=False, default="user")
    # Immutable actor-name snapshot captured at write time (§5).
    actor_display_name: Mapped[str | None] = mapped_column(String, nullable=True)

    # Use ACTION_* constants from app/audit/audit_constants.py
    action: Mapped[str] = mapped_column(String, nullable=False)
    # JSON snapshot before mutation
    old_value: Mapped[Any | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    # JSON snapshot after mutation
    new_value: Mapped[Any | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    # Structured context (e.g. client_record_id) — indexed via the §8b expression index.
    metadata_json: Mapped[Any | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    performed_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)

    # NOTE (dialect-specific exception): the §8b PostgreSQL expression index
    # ``idx_entity_audit_client_ctx`` on ((metadata_json->>'client_record_id'),
    # performed_at) is created in migration 0002 only. It is intentionally NOT
    # declared here because SQLAlchemy can't express a portable JSON ``->>``
    # expression index for SQLite create_all; SQLite dev/test may table-scan.
    __table_args__ = (
        Index("idx_entity_audit_entity_perf", "entity_type", "entity_id", "performed_at"),
        Index("idx_entity_audit_action_perf", "action", "performed_at"),
        Index("idx_entity_audit_performer_perf", "performed_by", "performed_at"),
        Index("idx_entity_audit_performed_at", "performed_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<EntityAuditLog(id={self.id}, entity_type={self.entity_type}, "
            f"entity_id={self.entity_id}, action={self.action})>"
        )
