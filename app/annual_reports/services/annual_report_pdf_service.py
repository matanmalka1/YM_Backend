"""Annual report PDF export — thin service wrapper."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.annual_reports.services.annual_report_pdf_builder import build_pdf
from app.annual_reports.services.detail_service import AnnualReportDetailService
from app.annual_reports.services.financial_summary_service import (
    AnnualReportFinancialSummaryService,
)
from app.annual_reports.services.messages import (
    ANNUAL_REPORT_NOT_FOUND,
    CLIENT_FALLBACK_NAME,
)
from app.annual_reports.services.tax_service import (
    AnnualReportTaxService,
)
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError


class AnnualReportPdfService:
    def __init__(self, db: Session):
        self.db = db
        self.client_repo = ClientRecordRepository(db)

    def generate(self, report_id: int) -> tuple[bytes, int]:
        repo = AnnualReportRepository(self.db)
        report = repo.get_by_id(report_id)
        if not report:
            raise NotFoundError(
                ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
                ErrorCode.ANNUAL_REPORT_NOT_FOUND,
            )

        client_record = self.client_repo.get_by_id(report.client_record_id)
        client_name = (
            f"לקוח {client_record.office_client_number}"
            if client_record and client_record.office_client_number
            else CLIENT_FALLBACK_NAME.format(client_record_id=report.client_record_id)
        )

        summary = AnnualReportFinancialSummaryService(self.db).get_financial_summary(report_id)
        tax = AnnualReportTaxService(self.db).get_tax_calculation(report_id)

        detail_svc = AnnualReportDetailService(self.db)
        detail = detail_svc.get_detail(report_id)

        return build_pdf(report, client_name, summary, tax, detail), report.tax_year


__all__ = ["AnnualReportPdfService"]
