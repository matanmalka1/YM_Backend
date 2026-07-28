from datetime import date
from decimal import Decimal

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


def test_advances_summary_reports_refund_when_advances_exceed_tax(
    client, test_db, advisor_headers, monkeypatch, annual_report_service_factory
):
    _patch_decimal_tax_input(monkeypatch)
    report = annual_report_service_factory()
    # No income/expense → tax_after_credits = 0

    repo = AdvancePaymentRepository(test_db)
    payment = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=report.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
        expected_amount=Decimal("100.00"),
        paid_amount=Decimal("100.00"),
        annual_report_id=report.id,
    )
    repo.update_payment(payment, status=ObligationStatus.SUBMITTED, paid_amount=Decimal("100.00"))

    resp = client.get(
        f"/api/v1/annual-reports/{report.id}/advances-summary",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert float(body["total_advances_paid"]) == 100.0
    assert body["advances_count"] == 1
    assert body["balance_type"] == "refund"
    assert float(body["final_balance"]) == -100.0


def test_advances_summary_zero_balance_without_paid_advances(
    client, advisor_headers, monkeypatch, annual_report_service_factory
):
    _patch_decimal_tax_input(monkeypatch)
    report = annual_report_service_factory()
    resp = client.get(
        f"/api/v1/annual-reports/{report.id}/advances-summary",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["balance_type"] == "zero"


def test_advances_summary_not_found(client, advisor_headers):
    resp = client.get("/api/v1/annual-reports/999999/advances-summary", headers=advisor_headers)
    assert resp.status_code == 404
