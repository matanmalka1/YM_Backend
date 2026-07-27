"""
EntityAuditLog — generic, append-only audit trail for domain mutations.

Design decisions:
- entity_type is String (not enum) — expands freely without migrations.
  Use ENTITY_* constants from app/audit/audit_constants.py.
- action is String — use ACTION_* constants, never raw strings in service code.
- old_value / new_value are JSONB snapshots of the changed fields only (not full rows).
  The writer persists dict/list objects directly, with no json.dumps wrapping.
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

from sqlalchemy import ForeignKey, Index, String, Text
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
    old_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    # JSON snapshot after mutation
    new_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    # Structured context (e.g. client_record_id) — indexed via the §8b expression index.
    metadata_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    performed_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)

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
