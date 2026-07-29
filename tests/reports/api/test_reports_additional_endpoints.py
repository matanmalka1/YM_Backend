from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.annual_reports.models.annual_report_enums import (
    ClientAnnualFilingType,
    FilingDeadlineType,
    PrimaryAnnualReportForm,
)
from app.annual_reports.models.annual_report_model import AnnualReport
from app.common.enums import ObligationStatus, VatType
from tests.helpers.tax_calendar_links import (
    create_tax_calendar_entry_for_annual,
    create_tax_calendar_entry_for_period,
)


def test_reports_vat_compliance_endpoint(
    client,
    test_db,
    advisor_headers,
    test_user,
    create_client_with_business,
    vat_work_item_factory,
):
    crm_client, business = create_client_with_business(
        full_name="Reports Client VAT", id_number="RPT-VAT", opened_at=date(2025, 1, 1)
    )
    now = datetime.now(UTC)
    jan_entry = create_tax_calendar_entry_for_period(test_db, "vat", "2026-01", 1)
    feb_entry = create_tax_calendar_entry_for_period(test_db, "vat", "2026-02", 1)
    dec_entry = create_tax_calendar_entry_for_period(test_db, "vat", "2025-12", 1)

    vat_work_item_factory(
        client_record_id=crm_client.id,
        created_by=test_user.id,
        period="2026-01",
        period_type=VatType.MONTHLY,
        status=ObligationStatus.SUBMITTED,
        closed_at=datetime(2026, 3, 1, 9, 0, 0),
        updated_at=now,
        tax_calendar_entry_id=jan_entry.id,
        due_date_original=jan_entry.due_date,
        due_date_effective=jan_entry.due_date,
    )
    vat_work_item_factory(
        client_record_id=crm_client.id,
        created_by=test_user.id,
        period="2026-02",
        period_type=VatType.MONTHLY,
        status=ObligationStatus.AWAITING_INPUT,
        updated_at=now - timedelta(days=40),
        tax_calendar_entry_id=feb_entry.id,
        due_date_original=feb_entry.due_date,
        due_date_effective=feb_entry.due_date,
    )
    vat_work_item_factory(
        client_record_id=crm_client.id,
        created_by=test_user.id,
        period="2025-12",
        period_type=VatType.MONTHLY,
        status=ObligationStatus.AWAITING_INPUT,
        updated_at=now - timedelta(days=45),
        tax_calendar_entry_id=dec_entry.id,
        due_date_original=dec_entry.due_date,
        due_date_effective=dec_entry.due_date,
    )
    test_db.commit()

    response = client.get("/api/v1/reports/vat-compliance?year=2026", headers=advisor_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["year"] == 2026
    assert payload["total_clients"] == 1
    assert payload["items"][0]["periods_expected"] == 2
    assert payload["items"][0]["periods_filed"] == 1
    assert payload["items"][0]["late_count"] == 1
    assert len(payload["stale_pending"]) == 1
    assert payload["stale_pending"][0]["period"] == "2026-02"
    assert payload["stale_pending"][0]["days_pending"] >= 40


def test_reports_advance_payments_endpoint_month_filter(
    client, test_db, advisor_headers, create_client_with_business, advance_payment_factory
):
    crm_client, _ = create_client_with_business(
        full_name="Reports Client ADV", id_number="RPT-ADV", opened_at=date(2025, 1, 1)
    )
    jan_entry = create_tax_calendar_entry_for_period(test_db, "advance_payment", "2026-01", 1)
    feb_entry = create_tax_calendar_entry_for_period(test_db, "advance_payment", "2026-02", 1)

    advance_payment_factory(
        client_record_id=crm_client.id,
        period="2026-01",
        period_months_count=1,
        expected_amount=Decimal("1000.00"),
        paid_amount=Decimal("500.00"),
        status=ObligationStatus.AWAITING_INPUT,
        due_date=date(2026, 1, 15),
        tax_calendar_entry_id=jan_entry.id,
    )
    advance_payment_factory(
        client_record_id=crm_client.id,
        period="2026-02",
        period_months_count=1,
        expected_amount=Decimal("700.00"),
        paid_amount=Decimal("700.00"),
        status=ObligationStatus.SUBMITTED,
        due_date=date(2026, 2, 15),
        tax_calendar_entry_id=feb_entry.id,
    )
    test_db.commit()

    response = client.get(
        "/api/v1/reports/advance-payments?year=2026&month=1",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["year"] == 2026
    assert payload["month"] == 1
    assert payload["total_expected"] == "1000.00"
    assert payload["total_paid"] == "500.00"
    assert payload["total_gap"] == "500.00"
    assert "business_id" not in payload["items"][0]
    assert "business_name" not in payload["items"][0]
    assert payload["items"][0]["office_client_number"] > 0
    assert payload["items"][0]["client_id_number"] == "RPT-ADV"
    assert payload["items"][0]["overdue_count"] == 1


def test_reports_annual_reports_endpoint(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, business = create_client_with_business(
        full_name="Reports Client ANR", id_number="RPT-ANR", opened_at=date(2025, 1, 1)
    )
    entry = create_tax_calendar_entry_for_annual(test_db, 2026)
    report = AnnualReport(
        client_record_id=crm_client.id,
        created_by=test_user.id,
        tax_year=2026,
        client_type=ClientAnnualFilingType.CORPORATION,
        form_type=PrimaryAnnualReportForm.FORM_1214,
        status=ObligationStatus.SUBMITTED,
        deadline_type=FilingDeadlineType.STANDARD,
        filing_deadline=datetime(2027, 4, 30, 0, 0, 0),
        tax_calendar_entry_id=entry.id,
    )
    test_db.add(report)
    test_db.commit()

    response = client.get("/api/v1/reports/annual-reports?tax_year=2026", headers=advisor_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["tax_year"] == 2026
    assert payload["total"] == 1
    assert payload["statuses"][0]["status"] == "submitted"
    assert payload["statuses"][0]["count"] == 1
    assert payload["statuses"][0]["clients"][0]["client_name"] == crm_client.full_name
    assert payload["statuses"][0]["clients"][0]["office_client_number"] > 0
    assert payload["statuses"][0]["clients"][0]["client_id_number"] == "RPT-ANR"
    assert payload["statuses"][0]["clients"][0]["filing_deadline"].endswith("Z")
    assert "T" in payload["statuses"][0]["clients"][0]["filing_deadline"]


def test_reports_aging_export_invalid_format_returns_422(client, advisor_headers):
    response = client.get("/api/v1/reports/aging/export?format=csv", headers=advisor_headers)
    assert response.status_code == 422
