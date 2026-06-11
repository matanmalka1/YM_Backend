"""Repository operations for annual report status audit rows."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.models.annual_report_status_history import (
    AnnualReportStatusHistory,
)


class AnnualReportStatusAuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def append_status_audit_entry(
        self,
        annual_report_id: int,
        from_status: AnnualReportStatus | None,
        to_status: AnnualReportStatus,
        changed_by: int,
        note: str | None = None,
    ) -> AnnualReportStatusHistory:
        entry = AnnualReportStatusHistory(
            annual_report_id=annual_report_id,
            from_status=from_status,
            to_status=to_status,
            changed_by=changed_by,
            note=note,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def list_status_audit_entries(self, annual_report_id: int) -> list[AnnualReportStatusHistory]:
        return self.db.scalars(
            select(AnnualReportStatusHistory)
            .where(AnnualReportStatusHistory.annual_report_id == annual_report_id)
            .order_by(AnnualReportStatusHistory.occurred_at.asc())
        ).all()
