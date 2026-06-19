from decimal import Decimal

from app.annual_reports.models.annual_report_expense_line import ExpenseCategoryType
from app.annual_reports.models.annual_report_income_line import IncomeSourceType
from app.annual_reports.repositories.annual_report_expense_repository import AnnualReportExpenseRepository
from app.annual_reports.repositories.annual_report_income_repository import AnnualReportIncomeRepository
from app.annual_reports.services.annual_report_service import AnnualReportService
from tests.helpers.identity import seed_client_identity


def _create_report(db, user, label: str):
    client = seed_client_identity(
        db,
        full_name=f"Financial Repo {label}",
        id_number=f"FR{label.zfill(7)}",
    )
    return AnnualReportService(db).create_report(
        client_record_id=client.id,
        tax_year=2026,
        client_type="corporation",
        created_by=user.id,
        created_by_name=user.full_name,
    )


def test_scoped_lookup_cannot_access_line_from_another_report(test_db, test_user):
    report_a = _create_report(test_db, test_user, "1")
    report_b = _create_report(test_db, test_user, "2")
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
