import pytest

from decimal import Decimal

from app.annual_reports.models.annual_report_expense_line import ExpenseCategoryType
from app.annual_reports.models.annual_report_income_line import IncomeSourceType
from app.annual_reports.repositories.expense_repository import AnnualReportExpenseRepository
from app.annual_reports.repositories.income_repository import AnnualReportIncomeRepository
from app.annual_reports.services.annual_report_service import AnnualReportService
from tests.helpers.identity import seed_client_identity


@pytest.mark.parametrize(
    ("repo_cls", "method_name"),
    [
        (AnnualReportIncomeRepository, "get_by_id"),
        (AnnualReportIncomeRepository, "update"),
        (AnnualReportIncomeRepository, "delete"),
        (AnnualReportExpenseRepository, "get_by_id"),
        (AnnualReportExpenseRepository, "update"),
        (AnnualReportExpenseRepository, "delete"),
    ],
)
def test_unscoped_financial_line_repository_methods_do_not_exist(test_db, repo_cls, method_name):
    repo = repo_cls(test_db)

    assert not hasattr(repo, method_name)


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


def test_apply_updates_uses_preloaded_entity_without_reload(test_db, test_user, monkeypatch):
    report = _create_report(test_db, test_user, "3")
    repo = AnnualReportIncomeRepository(test_db)
    line = repo.create_for_report(
        report.id,
        IncomeSourceType.SALARY,
        Decimal("100.00"),
    )

    def _fail_reload(*_args, **_kwargs):
        raise AssertionError("apply_updates must not reload")

    monkeypatch.setattr(repo, "get_by_report_and_line_id", _fail_reload)

    updated = repo.apply_updates(line, {"amount": Decimal("125.00")})

    assert updated is line
    assert line.amount == Decimal("125.00")


def test_delete_line_uses_preloaded_entity_without_reload(test_db, test_user, monkeypatch):
    report = _create_report(test_db, test_user, "4")
    repo = AnnualReportExpenseRepository(test_db)
    line = repo.create_for_report(
        report.id,
        ExpenseCategoryType.OFFICE_RENT,
        Decimal("50.00"),
        Decimal("1.00"),
    )
    line_id = line.id

    def _fail_reload(*_args, **_kwargs):
        raise AssertionError("delete_line must not reload")

    monkeypatch.setattr(repo, "get_by_report_and_line_id", _fail_reload)

    repo.delete_line(line)

    assert test_db.get(type(line), line_id) is None
