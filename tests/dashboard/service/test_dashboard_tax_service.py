from types import SimpleNamespace

from app.dashboard.services.dashboard_tax_service import DashboardTaxService


def test_get_submission_widget_data_defaults_to_current_year(monkeypatch, test_db):
    service = DashboardTaxService(test_db)
    monkeypatch.setattr(
        "app.dashboard.services.dashboard_tax_service.israel_today",
        lambda: SimpleNamespace(year=2035),
    )

    calls = []

    def _count_by_status(_status, tax_year):
        calls.append(tax_year)
        return 0

    service.business_repo = SimpleNamespace(count=lambda **kwargs: 0)
    service.report_repo = SimpleNamespace(
        count_by_status=_count_by_status,
        sum_financials_by_year=lambda year: {"total_refund_due": 0, "total_tax_due": 0},
    )

    result = service.get_submission_widget_data()

    assert result["tax_year"] == 2035
    assert result["submission_percentage"] == 0.0
    assert calls and all(year == 2035 for year in calls)
