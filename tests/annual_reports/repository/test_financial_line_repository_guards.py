import pytest

from app.annual_reports.repositories.expense_repository import AnnualReportExpenseRepository
from app.annual_reports.repositories.income_repository import AnnualReportIncomeRepository


@pytest.mark.parametrize(
    ("repo_cls", "method_name", "args"),
    [
        (AnnualReportIncomeRepository, "get_by_id", (1,)),
        (AnnualReportIncomeRepository, "update", (1,)),
        (AnnualReportIncomeRepository, "delete", (1,)),
        (AnnualReportExpenseRepository, "get_by_id", (1,)),
        (AnnualReportExpenseRepository, "update", (1,)),
        (AnnualReportExpenseRepository, "delete", (1,)),
    ],
)
def test_unscoped_financial_line_repository_methods_are_disabled(
    test_db, repo_cls, method_name, args
):
    repo = repo_cls(test_db)

    with pytest.raises(NotImplementedError, match="unsafe"):
        getattr(repo, method_name)(*args)
