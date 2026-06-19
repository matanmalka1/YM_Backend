from datetime import date
from decimal import Decimal

from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.annual_reports.services.annual_report_ni_engine import (
    calculate_national_insurance as _calculate_ni,
)
from app.annual_reports.services.annual_report_tax_engine import calculate_tax as _calculate_tax
from tests.helpers.identity import seed_client_identity
from tests.helpers.tax_calendar_links import create_linked_advance_payment


def _create_report(db):
    client = seed_client_identity(db, full_name="Advances Client", id_number="878787878")

    svc = AnnualReportService(db)
    return svc.create_report(
        client_record_id=client.id,
        tax_year=2026,
        client_type="corporation",
        created_by=1,
        created_by_name="Tester",
        deadline_type="standard",
    )


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
    client, test_db, advisor_headers, monkeypatch
):
    _patch_decimal_tax_input(monkeypatch)
    report = _create_report(test_db)
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
    repo.update_payment(payment, status=AdvancePaymentStatus.PAID, paid_amount=Decimal("100.00"))

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
    client, test_db, advisor_headers, monkeypatch
):
    _patch_decimal_tax_input(monkeypatch)
    report = _create_report(test_db)
    resp = client.get(
        f"/api/v1/annual-reports/{report.id}/advances-summary",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["balance_type"] == "zero"


def test_advances_summary_not_found(client, advisor_headers):
    resp = client.get("/api/v1/annual-reports/999999/advances-summary", headers=advisor_headers)
    assert resp.status_code == 404
