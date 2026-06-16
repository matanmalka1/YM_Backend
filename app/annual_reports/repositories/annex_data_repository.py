"""Repository for AnnualReportAnnexData entities."""

from sqlalchemy import func, select

from app.annual_reports.models.annual_report_annex_data import AnnualReportAnnexData
from app.annual_reports.models.annual_report_enums import AnnualReportSchedule
from app.annual_reports.models.annual_report_schedule_entry import (
    AnnualReportScheduleEntry,
)
from app.common.repositories.base_repository import BaseRepository


class AnnexDataRepository(BaseRepository[AnnualReportAnnexData]):
    model = AnnualReportAnnexData

    def list_by_report_and_schedule(
        self, report_id: int, schedule: AnnualReportSchedule
    ) -> list[AnnualReportAnnexData]:
        return self.db.scalars(
            select(AnnualReportAnnexData)
            .join(AnnualReportAnnexData.schedule_entry)
            .where(
                AnnualReportScheduleEntry.annual_report_id == report_id,
                AnnualReportScheduleEntry.schedule == schedule,
            )
            .order_by(AnnualReportAnnexData.line_number.asc())
        ).all()

    def get_schedule_entry(
        self, report_id: int, schedule: AnnualReportSchedule
    ) -> AnnualReportScheduleEntry | None:
        return self.db.scalars(
            select(AnnualReportScheduleEntry).where(
                AnnualReportScheduleEntry.annual_report_id == report_id,
                AnnualReportScheduleEntry.schedule == schedule,
            )
        ).first()

    def get_or_create_schedule_entry(
        self, report_id: int, schedule: AnnualReportSchedule
    ) -> AnnualReportScheduleEntry:
        entry = self.get_schedule_entry(report_id, schedule)
        if entry:
            return entry
        entry = AnnualReportScheduleEntry(
            annual_report_id=report_id,
            schedule=schedule,
            is_required=False,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def next_line_number(self, schedule_entry_id: int) -> int:
        current_max = self.db.scalar(
            select(func.max(AnnualReportAnnexData.line_number)).where(
                AnnualReportAnnexData.schedule_entry_id == schedule_entry_id
            )
        )
        return int(current_max or 0) + 1

    def add_line(
        self,
        schedule_entry_id: int,
        line_number: int,
        data: dict,
        notes: str | None = None,
    ) -> AnnualReportAnnexData:
        row = AnnualReportAnnexData(
            schedule_entry_id=schedule_entry_id,
            line_number=line_number,
            data=data,
            notes=notes,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def update_line(
        self, line_id: int, data: dict, notes: str | None = None
    ) -> AnnualReportAnnexData | None:
        row = self.get_by_id(line_id)
        if not row:
            return None
        row.data = data
        if notes is not None:
            row.notes = notes
        self.db.flush()
        return row

    def delete_line(self, line_id: int) -> bool:
        # Intentional hard-delete. Service layer snapshots the row to generic audit first.
        row = self.get_by_id(line_id)
        if not row:
            return False
        self.db.delete(row)
        self.db.flush()
        return True

    def count_by_report_and_schedule(self, report_id: int, schedule: AnnualReportSchedule) -> int:
        return self.db.scalar(
            select(func.count(AnnualReportAnnexData.id))
            .join(AnnualReportAnnexData.schedule_entry)
            .where(
                AnnualReportScheduleEntry.annual_report_id == report_id,
                AnnualReportScheduleEntry.schedule == schedule,
            )
        )


__all__ = ["AnnexDataRepository"]
