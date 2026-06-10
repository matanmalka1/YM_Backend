"""
Correspondence — log of all interactions with a client, business, or authority contact.

Israeli context:
  Tax advisors maintain detailed correspondence logs for audit purposes and
  ITA disputes. Entries cover calls with the tax authority, letters sent,
  meetings with clients, and email exchanges.

Design decisions:
- client_record_id is the primary anchor (legal entity record).
- business_id is OPTIONAL context — set when the correspondence is scoped
  to a specific business activity (UI grouping only).
- occurred_at is DateTime(timezone=True) — stored as UTC, frontend converts to Asia/Jerusalem.
- contact_id links to AuthorityContact (רשות המסים, ביטוח לאומי, etc.) —
  nullable because not all correspondence involves an authority contact.
- No updated_at — correspondence entries are immutable once created;
  corrections are soft-deleted and re-entered.
- Soft delete included — business entity.
"""

from __future__ import annotations

import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow_aware

if TYPE_CHECKING:
    from app.authority_contact.models.authority_contact import AuthorityContact


class CorrespondenceType(str, PyEnum):
    CALL = "call"  # שיחת טלפון
    LETTER = "letter"  # מכתב / דואר רשום
    EMAIL = "email"  # דואר אלקטרוני
    MEETING = "meeting"  # פגישה פיזית או זום
    FAX = "fax"  # פקס (תקשורת חוקית עם רשויות מס)


class Correspondence(Base):
    __tablename__ = "correspondence_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ── Anchors ───────────────────────────────────────────────────────────────
    client_record_id: Mapped[int] = mapped_column(
        ForeignKey("client_records.id"), nullable=False, index=True
    )
    # OPTIONAL: set when the correspondence is scoped to a specific business
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    # OPTIONAL: authority contact involved (רשות המסים, ביטוח לאומי, etc.)
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("authority_contacts.id"), nullable=True, index=True
    )

    # ── Content ───────────────────────────────────────────────────────────────
    correspondence_type: Mapped[CorrespondenceType] = mapped_column(
        pg_enum(CorrespondenceType), nullable=False
    )
    subject: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime.datetime] = mapped_column(
        nullable=False  # UTC; מתי התרחש האירוע בפועל — frontend converts to Asia/Jerusalem
    )

    # ── Metadata ──────────────────────────────────────────────────────────────
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(default=utcnow_aware, nullable=False)

    # ── Soft delete ───────────────────────────────────────────────────────────
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    contact: Mapped["AuthorityContact | None"] = relationship(
        "AuthorityContact", foreign_keys="[Correspondence.contact_id]", viewonly=True
    )

    __table_args__ = (
        Index("idx_correspondence_business_occurred", "business_id", "occurred_at"),
        Index("idx_correspondence_occurred", "occurred_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Correspondence(id={self.id}, client_record_id={self.client_record_id}, "
            f"business_id={self.business_id}, type='{self.correspondence_type}', "
            f"occurred='{self.occurred_at}')>"
        )
