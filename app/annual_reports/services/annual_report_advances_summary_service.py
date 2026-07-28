"""Advances summary — links advance payments to an annual report."""

from sqlalchemy.orm import Session

from app.advance_payments.repositories.advance_payment_aggregation_repository import (
    AdvancePaymentAggregationRepository,
)
from app.annual_reports.annual_report_messages import ANNUAL_REPORT_NOT_FOUND
from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.annual_reports.schemas.annual_report_financials import AdvancesSummary
from app.annual_reports.services.annual_report_tax_service import (
    AnnualReportTaxService,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError


class AnnualReportAdvancesSummaryService:
    def __init__(self, db: Session):
        self.db = db
        self.report_repo = AnnualReportRepository(db)
        self.aggregation_repo = AdvancePaymentAggregationRepository(db)

    def get_advances_summary(self, report_id: int) -> AdvancesSummary:
        report = self.report_repo.get_by_id(report_id)
        if not report:
            raise NotFoundError(
                ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
                ErrorCode.ANNUAL_REPORT_NOT_FOUND,
            )
        return self.get_advances_summary_for_report(report)

    def get_advances_summary_for_report(self, report: AnnualReport) -> AdvancesSummary:
        # The total and the balance come from the tax service, which reads the SQL
        # aggregate. This used to sum a page-capped read of up to 10000 rows in
        # Python, which silently undercounted past the cap and could disagree with
        # the same figure on the report detail response.
        tax_result = AnnualReportTaxService(self.db).get_tax_calculation_for_report(report)
        total = tax_result.advances_paid
        balance = tax_result.final_balance
        count = self.aggregation_repo.count_paid_by_client_year(
            report.client_record_id, report.tax_year
        )

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
