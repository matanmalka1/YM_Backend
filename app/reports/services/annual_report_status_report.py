"""Service for the annual report status report grouped by status."""

from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.utils.time_utils import israel_today


class AnnualReportStatusReportService:
    def __init__(self, db: Session):
        self.repo = AnnualReportRepository(db)

    def get_report(self, tax_year: int) -> dict:
        rows = self.repo.list_by_tax_year_with_client(tax_year)

        today = israel_today()
        grouped: dict[str, list] = {s.value: [] for s in AnnualReportStatus}

        for report, client_record_id, client_name in rows:
            filing_deadline_date = None
            if report.filing_deadline:
                filing_deadline_date = (
                    report.filing_deadline.date()
                    if hasattr(report.filing_deadline, "date")
                    else report.filing_deadline
                )
            days_until = (filing_deadline_date - today).days if filing_deadline_date else None

            grouped[report.status.value].append(
                {
                    "client_record_id": client_record_id,
                    "client_name": client_name,
                    "form_type": report.form_type.value if report.form_type else None,
                    "filing_deadline": filing_deadline_date,
                    "days_until_deadline": days_until,
                }
            )

        statuses = [
            {
                "status": status_value,
                "count": len(clients),
                "clients": clients,
            }
            for status_value, clients in grouped.items()
            if clients
        ]

        return {
            "tax_year": tax_year,
            "total": len(rows),
            "statuses": statuses,
        }
