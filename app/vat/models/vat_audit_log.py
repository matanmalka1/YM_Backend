from __future__ import annotations

"""
VAT Audit Log — append-only audit trail for every work item action.

Design decisions:
- action is String (not enum) — expands freely without migrations.
  Use ACTION_* constants from vat_reports/services/constants.py.
- invoice_id is a direct FK for efficient per-invoice history queries.
  SET NULL on invoice delete — log entry is preserved even if invoice is gone.
- NO soft delete — audit logs are immutable by design.
  Corrections are made by appending new entries, never deleting old ones.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.time_utils import utcnow


class VatAuditLog(Base):
    __tablename__ = "vat_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    work_item_id: Mapped[int] = mapped_column(
        ForeignKey("vat_work_items.id"), nullable=False, index=True
    )
    performed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Use ACTION_* constants from constants.py — never raw strings in service code
    action: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON snapshot
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON snapshot
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Direct FK for efficient "show history of invoice X" queries
    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("vat_invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    performed_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)

    def __repr__(self) -> str:
        return (
            f"<VatAuditLog(id={self.id}, work_item_id={self.work_item_id}, action={self.action})>"
        )
