"""
EntityNote — centralized notes attached to any domain entity.

Design decisions:
- entity_type is String so it can represent any domain without migrations.
- entity_id identifies the target row in that domain.
- note stores the note body.
- records are mutable and soft-deletable, matching the rest of the codebase.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.time_utils import utcnow


class EntityNote(Base):
    __tablename__ = "entity_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(nullable=False, index=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    __table_args__ = (Index("idx_entity_notes_type_id", "entity_type", "entity_id"),)

    def __repr__(self) -> str:
        return (
            f"<EntityNote(id={self.id}, entity_type={self.entity_type}, "
            f"entity_id={self.entity_id})>"
        )
