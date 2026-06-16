"""Advances summary — links advance payments to an annual report."""

from app.core.error_codes import ErrorCode
from decimal import Decimal

from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.annual_reports.schemas.annual_report_financials import AdvancesSummary
from app.annual_reports.services.messages import ANNUAL_REPORT_NOT_FOUND
from app.annual_reports.services.tax_service import (
    AnnualReportTaxService,
)
from app.core.exceptions import NotFoundError


class AnnualReportAdvancesSummaryService:
    def __init__(self, db: Session):
        self.db = db
        self.report_repo = AnnualReportRepository(db)
        self.advance_repo = AdvancePaymentRepository(db)

    def get_advances_summary(self, report_id: int) -> AdvancesSummary:
        report = self.report_repo.get_by_id(report_id)
        if not report:
            raise NotFoundError(
                ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
                ErrorCode.ANNUAL_REPORT_NOT_FOUND,
            )
        return self.get_advances_summary_for_report(report)

    def get_advances_summary_for_report(self, report: AnnualReport) -> AdvancesSummary:
        payments, count = self.advance_repo.list_by_client_record_year(
            report.client_record_id,
            report.tax_year,
            status=[AdvancePaymentStatus.PAID],
            page=1,
            page_size=10000,
        )

        total = sum((p.paid_amount or Decimal("0")) for p in payments)

        tax_result = AnnualReportTaxService(self.db).get_tax_calculation_for_report(report)
        balance = tax_result.tax_after_credits - total

        if balance > 0:
            balance_type = "due"
        elif balance < 0:
            balance_type = "refund"
        else:
            balance_type = "zero"

        return AdvancesSummary(
            total_advances_paid=round(total, 2),
            advances_count=count,
            final_balance=round(balance, 2),
            balance_type=balance_type,
        )


__all__ = ["AnnualReportAdvancesSummaryService"]
