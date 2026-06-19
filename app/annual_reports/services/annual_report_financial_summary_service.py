"""Annual report financial summary service."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.annual_reports.repositories.annual_report_expense_repository import (
    AnnualReportExpenseRepository,
)
from app.annual_reports.repositories.annual_report_income_repository import (
    AnnualReportIncomeRepository,
)
from app.annual_reports.schemas.annual_report_financials import (
    ExpenseLineResponse,
    FinancialSummaryResponse,
    IncomeLineResponse,
)
from app.annual_reports.annual_report_messages import ANNUAL_REPORT_NOT_FOUND
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError


class AnnualReportFinancialSummaryService:
    """Build income, expense, and taxable-income summaries."""

    def __init__(self, db: Session):
        self.report_repo = AnnualReportRepository(db)
        self.income_repo = AnnualReportIncomeRepository(db)
        self.expense_repo = AnnualReportExpenseRepository(db)

    def get_financial_summary(self, report_id: int) -> FinancialSummaryResponse:
        report = self.report_repo.get_by_id(report_id)
        if not report:
            raise NotFoundError(
                ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
                ErrorCode.ANNUAL_REPORT_NOT_FOUND,
            )
        return self.get_financial_summary_for_report(report)

    def get_financial_summary_for_report(self, report: AnnualReport) -> FinancialSummaryResponse:
        income_lines = self.income_repo.list_by_report(report.id)
        expense_lines = self.expense_repo.list_by_report(report.id)
        total_income = sum((line.amount for line in income_lines), Decimal("0"))
        gross_expenses = sum((line.amount for line in expense_lines), Decimal("0"))
        recognized_expenses = sum(
            (line.amount * line.recognition_rate for line in expense_lines),
            Decimal("0"),
        )
        return FinancialSummaryResponse(
            annual_report_id=report.id,
            total_income=float(total_income),
            gross_expenses=float(gross_expenses),
            recognized_expenses=float(recognized_expenses),
            taxable_income=float(total_income - recognized_expenses),
            income_lines=[IncomeLineResponse.model_validate(line) for line in income_lines],
            expense_lines=[ExpenseLineResponse.model_validate(line) for line in expense_lines],
        )


__all__ = ["AnnualReportFinancialSummaryService"]
