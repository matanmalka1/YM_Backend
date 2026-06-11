"""Append-only status history for annual reports."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class AnnualReportStatusHistory(Base):
    """Audit trail for every status change on an annual report.

    Append-only — no soft delete, no updated_at.
    """

    __tablename__ = "annual_report_status_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    annual_report_id: Mapped[int] = mapped_column(
        ForeignKey("annual_reports.id"), nullable=False, index=True
    )
    from_status: Mapped[AnnualReportStatus | None] = mapped_column(
        pg_enum(AnnualReportStatus), nullable=True
    )
    to_status: Mapped[AnnualReportStatus] = mapped_column(
        pg_enum(AnnualReportStatus), nullable=False
    )
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)


__all__ = ["AnnualReportStatusHistory"]
