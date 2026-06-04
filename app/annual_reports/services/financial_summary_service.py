"""Annual report financial summary service."""

from sqlalchemy.orm import Session

from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.annual_reports.repositories.expense_repository import (
    AnnualReportExpenseRepository,
)
from app.annual_reports.repositories.income_repository import (
    AnnualReportIncomeRepository,
)
from app.annual_reports.schemas.annual_report_financials import (
    ExpenseLineResponse,
    FinancialSummaryResponse,
    IncomeLineResponse,
)
from app.annual_reports.services.messages import ANNUAL_REPORT_NOT_FOUND
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
                "ANNUAL_REPORT.NOT_FOUND",
            )

        income_lines = self.income_repo.list_by_report(report_id)
        expense_lines = self.expense_repo.list_by_report(report_id)
        total_income = self.income_repo.total_income(report_id)
        gross_expenses = self.expense_repo.total_expenses(report_id)
        recognized_expenses = self.expense_repo.total_recognized_expenses(report_id)
        return FinancialSummaryResponse(
            annual_report_id=report_id,
            total_income=float(total_income),
            gross_expenses=float(gross_expenses),
            recognized_expenses=float(recognized_expenses),
            taxable_income=float(total_income - recognized_expenses),
            income_lines=[IncomeLineResponse.model_validate(line) for line in income_lines],
            expense_lines=[ExpenseLineResponse.model_validate(line) for line in expense_lines],
        )


__all__ = ["AnnualReportFinancialSummaryService"]
