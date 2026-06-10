"""Repository operations for annual report schedules."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_enums import AnnualReportSchedule
from app.annual_reports.models.annual_report_schedule_entry import (
    AnnualReportScheduleEntry,
)
from app.utils.time_utils import utcnow


class AnnualReportScheduleRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_schedule(
        self,
        annual_report_id: int,
        schedule: AnnualReportSchedule,
        is_required: bool = True,
        notes: str | None = None,
    ) -> AnnualReportScheduleEntry:
        entry = AnnualReportScheduleEntry(
            annual_report_id=annual_report_id,
            schedule=schedule,
            is_required=is_required,
            notes=notes,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def get_schedules(self, annual_report_id: int) -> list[AnnualReportScheduleEntry]:
        return self.db.scalars(
            select(AnnualReportScheduleEntry)
            .where(AnnualReportScheduleEntry.annual_report_id == annual_report_id)
            .order_by(AnnualReportScheduleEntry.schedule.asc())
        ).all()

    def mark_schedule_complete(
        self, annual_report_id: int, schedule: AnnualReportSchedule
    ) -> AnnualReportScheduleEntry | None:
        entry = self.db.scalars(
            select(AnnualReportScheduleEntry).where(
                AnnualReportScheduleEntry.annual_report_id == annual_report_id,
                AnnualReportScheduleEntry.schedule == schedule,
            )
        ).first()
        if not entry:
            return None
        entry.is_complete = True
        entry.completed_at = utcnow()
        self.db.flush()
        return entry

    def schedules_complete(self, annual_report_id: int) -> bool:
        """True if all required schedules are marked complete."""
        required = self.db.scalars(
            select(AnnualReportScheduleEntry).where(
                AnnualReportScheduleEntry.annual_report_id == annual_report_id,
                AnnualReportScheduleEntry.is_required.is_(True),
            )
        ).all()
        return all(s.is_complete for s in required)
