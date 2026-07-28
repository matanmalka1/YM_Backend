"""``final_balance`` must be one number, whichever endpoint publishes it.

It used to be computed twice from different data sources — the report detail read
the SQL aggregate, while the advances summary summed ``paid_amount`` in Python over
a ``page_size=10000`` read. Same formula, different inputs, so the two could
disagree for one report and the summary silently undercounted past its page cap.

AnnualReportTaxService now publishes ``advances_paid`` and ``final_balance``, and
every consumer reads them. These tests pin that they agree.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.annual_reports.annual_report_ni_engine import (
    calculate_national_insurance as _calculate_ni,
)
from app.annual_reports.annual_report_tax_engine import calculate_tax as _calculate_tax
from app.common.enums import ObligationStatus
from tests.helpers.tax_calendar_links import create_linked_advance_payment


def _patch_decimal_tax_input(monkeypatch):
    monkeypatch.setattr(
        "app.annual_reports.services.annual_report_tax_service.calculate_tax",
        lambda taxable_income, *args, **kwargs: _calculate_tax(
            float(taxable_income), *args, **kwargs
        ),
    )
    monkeypatch.setattr(
        "app.annual_reports.services.annual_report_tax_service.calculate_national_insurance",
        lambda income, *args, **kwargs: _calculate_ni(float(income), *args, **kwargs),
    )


def _pay(test_db, report, period: str, due_day: date, amount: str):
    repo = AdvancePaymentRepository(test_db)
    payment = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=report.client_record_id,
        period=period,
        period_months_count=1,
        due_date=due_day,
        expected_amount=Decimal(amount),
        paid_amount=Decimal(amount),
        annual_report_id=report.id,
    )
    repo.update_payment(payment, status=ObligationStatus.SUBMITTED, paid_amount=Decimal(amount))
    return payment


@pytest.fixture
def report_with_advances(test_db, monkeypatch, annual_report_service_factory):
    _patch_decimal_tax_input(monkeypatch)
    report = annual_report_service_factory()
    _pay(test_db, report, "2026-01", date(2026, 2, 15), "150.00")
    _pay(test_db, report, "2026-02", date(2026, 3, 15), "250.00")
    return report


def test_detail_and_advances_summary_publish_the_same_final_balance(
    client, advisor_headers, report_with_advances
):
    report = report_with_advances

    detail = client.get(f"/api/v1/annual-reports/{report.id}", headers=advisor_headers)
    summary = client.get(
        f"/api/v1/annual-reports/{report.id}/advances-summary", headers=advisor_headers
    )
    assert detail.status_code == 200
    assert summary.status_code == 200

    detail_balance = Decimal(str(detail.json()["tax_calculation"]["final_balance"]))
    summary_balance = Decimal(str(summary.json()["final_balance"]))
    assert detail_balance == summary_balance


def test_tax_calculation_endpoint_agrees_too(client, advisor_headers, report_with_advances):
    report = report_with_advances

    tax = client.get(f"/api/v1/annual-reports/{report.id}/tax-calculation", headers=advisor_headers)
    summary = client.get(
        f"/api/v1/annual-reports/{report.id}/advances-summary", headers=advisor_headers
    )
    assert tax.status_code == 200
    assert summary.status_code == 200

    assert Decimal(str(tax.json()["final_balance"])) == Decimal(
        str(summary.json()["final_balance"])
    )
    assert Decimal(str(tax.json()["advances_paid"])) == Decimal(
        str(summary.json()["total_advances_paid"])
    )


def test_advances_paid_is_the_sum_of_paid_rows(client, advisor_headers, report_with_advances):
    """400.00 across two PAID rows — the aggregate, not a page of rows."""
    report = report_with_advances

    tax = client.get(f"/api/v1/annual-reports/{report.id}/tax-calculation", headers=advisor_headers)
    assert Decimal(str(tax.json()["advances_paid"])) == Decimal("400.00")


def test_unpaid_advances_are_excluded(
    client, test_db, advisor_headers, monkeypatch, annual_report_service_factory
):
    """A PENDING row contributes nothing, in both publishers."""
    _patch_decimal_tax_input(monkeypatch)
    report = annual_report_service_factory()
    repo = AdvancePaymentRepository(test_db)
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=report.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
        expected_amount=Decimal("500.00"),
        paid_amount=Decimal("0.00"),
        annual_report_id=report.id,
    )

    tax = client.get(f"/api/v1/annual-reports/{report.id}/tax-calculation", headers=advisor_headers)
    summary = client.get(
        f"/api/v1/annual-reports/{report.id}/advances-summary", headers=advisor_headers
    )

    assert Decimal(str(tax.json()["advances_paid"])) == Decimal("0.00")
    assert Decimal(str(summary.json()["total_advances_paid"])) == Decimal("0.00")
    assert summary.json()["advances_count"] == 0
