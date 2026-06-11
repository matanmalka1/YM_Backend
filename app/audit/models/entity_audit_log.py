"""
EntityAuditLog — generic, append-only audit trail for domain mutations.

Design decisions:
- entity_type is String (not enum) — expands freely without migrations.
  Use ENTITY_* constants from app/audit/constants.py.
- action is String — use ACTION_* constants, never raw strings in service code.
- old_value / new_value are JSON snapshots of the changed fields only (not full rows).
- NO soft delete — audit logs are immutable by design.
  Corrections are made by appending new entries, never deleting old ones.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.time_utils import utcnow


class EntityAuditLog(Base):
    __tablename__ = "entity_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(nullable=False, index=True)
    performed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Use ACTION_* constants from app/audit/constants.py
    action: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON snapshot before mutation
    new_value: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON snapshot after mutation
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    performed_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)

    __table_args__ = (Index("idx_entity_audit_type_id", "entity_type", "entity_id"),)

    def __repr__(self) -> str:
        return (
            f"<EntityAuditLog(id={self.id}, entity_type={self.entity_type}, "
            f"entity_id={self.entity_id}, action={self.action})>"
        )
