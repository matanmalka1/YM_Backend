from __future__ import annotations

"""Annex (schedule) data lines for an annual report."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    ForeignKey,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.time_utils import utcnow

if TYPE_CHECKING:
    from app.annual_reports.models.annual_report_schedule_entry import AnnualReportScheduleEntry


class AnnualReportAnnexData(Base):
    """Flexible per-schedule data line attached to an annual report."""

    __tablename__ = "annual_report_annex_data"
    __table_args__ = (
        UniqueConstraint(
            "schedule_entry_id",
            "line_number",
            name="uq_annual_report_annex_data_schedule_entry_line",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    schedule_entry_id: Mapped[int] = mapped_column(
        ForeignKey("annual_report_schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_number: Mapped[int] = mapped_column(nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    data_version: Mapped[int] = mapped_column(nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, onupdate=utcnow)
    schedule_entry: Mapped[AnnualReportScheduleEntry] = relationship(
        "AnnualReportScheduleEntry", back_populates="annex_lines"
    )

    @hybrid_property
    def annual_report_id(self):
        return self.schedule_entry.annual_report_id

    @hybrid_property
    def schedule(self):
        return self.schedule_entry.schedule

    def __repr__(self):
        return (
            f"<AnnualReportAnnexData(id={self.id}, report_id={self.annual_report_id}, "
            f"schedule={self.schedule}, line={self.line_number})>"
        )


__all__ = ["AnnualReportAnnexData"]
