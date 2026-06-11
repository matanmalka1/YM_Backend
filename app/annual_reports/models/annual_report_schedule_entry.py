"""Annual report schedule entries (annex tracking)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    ForeignKey,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.annual_reports.models.annual_report_enums import AnnualReportSchedule
from app.database import Base

if TYPE_CHECKING:
    from app.annual_reports.models.annual_report_annex_data import AnnualReportAnnexData
    from app.annual_reports.models.annual_report_model import AnnualReport
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class AnnualReportScheduleEntry(Base):
    """
    Tracks required schedules for an annual report and their completion status.
    """

    __tablename__ = "annual_report_schedules"
    __table_args__ = (
        UniqueConstraint(
            "annual_report_id",
            "schedule",
            name="uq_annual_report_schedules_report_schedule",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    annual_report_id: Mapped[int] = mapped_column(
        ForeignKey("annual_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    schedule: Mapped[AnnualReportSchedule] = mapped_column(
        pg_enum(AnnualReportSchedule, create_type=False), nullable=False
    )
    is_required: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_complete: Mapped[bool] = mapped_column(default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    annual_report: Mapped[AnnualReport] = relationship(
        "AnnualReport", back_populates="schedule_entries"
    )
    annex_lines: Mapped[list[AnnualReportAnnexData]] = relationship(
        "AnnualReportAnnexData",
        back_populates="schedule_entry",
        cascade="all, delete-orphan",
        lazy="select",
    )


__all__ = ["AnnualReportScheduleEntry"]
