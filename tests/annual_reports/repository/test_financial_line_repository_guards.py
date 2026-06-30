from decimal import Decimal

from app.annual_reports.models.annual_report_expense_line import ExpenseCategoryType
from app.annual_reports.models.annual_report_income_line import IncomeSourceType
from app.annual_reports.repositories.annual_report_expense_repository import (
    AnnualReportExpenseRepository,
)
from app.annual_reports.repositories.annual_report_income_repository import (
    AnnualReportIncomeRepository,
)


def test_scoped_lookup_cannot_access_line_from_another_report(
    test_db, test_user, annual_report_factory
):
    report_a = annual_report_factory(actor=test_user)
    report_b = annual_report_factory(actor=test_user)
    income_repo = AnnualReportIncomeRepository(test_db)
    expense_repo = AnnualReportExpenseRepository(test_db)

    income = income_repo.create_for_report(
        report_a.id,
        IncomeSourceType.SALARY,
        Decimal("100.00"),
    )
    expense = expense_repo.create_for_report(
        report_a.id,
        ExpenseCategoryType.OFFICE_RENT,
        Decimal("50.00"),
        Decimal("1.00"),
    )

    assert income_repo.get_by_report_and_line_id(report_b.id, income.id) is None
    assert expense_repo.get_by_report_and_line_id(report_b.id, expense.id) is None
