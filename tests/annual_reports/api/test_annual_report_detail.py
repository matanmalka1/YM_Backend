from app.annual_reports.services.annual_report_service import AnnualReportService
from tests.helpers.identity import seed_client_identity


def _create_report(test_db):
    client = seed_client_identity(test_db, full_name="Annual Report Client", id_number="333333333")

    service = AnnualReportService(test_db)
    report = service.create_report(
        client_record_id=client.id,
        tax_year=2025,
        client_type="corporation",
        created_by=1,
        created_by_name="Test User",
        deadline_type="custom",
        notes=None,
    )
    return report


def test_get_detail_returns_blank_when_missing(client, test_db, advisor_headers):
    report = _create_report(test_db)

    response = client.get(
        f"/api/v1/annual-reports/{report.id}/details",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["report_id"] == report.id
    assert data["pension_contribution"] is None
    assert data["donation_amount"] is None
    assert data["other_credits"] is None
    assert data["client_approved_at"] is None
    assert data["internal_notes"] is None
    # Dead duplicate float copies removed (api-todo 35b). Canonical refund_due/
    # tax_due live on the main report DTO, not on ReportDetailResponse.
    assert "tax_refund_amount" not in data
    assert "tax_due_amount" not in data


def test_update_detail_creates_and_updates(client, test_db, advisor_headers):
    report = _create_report(test_db)

    first_response = client.patch(
        f"/api/v1/annual-reports/{report.id}/details",
        headers=advisor_headers,
        json={
            "pension_contribution": 1200.5,
            "donation_amount": 300.0,
            "client_approved_at": "2026-02-15T12:00:00",
            "internal_notes": "Initial review complete",
        },
    )

    assert first_response.status_code == 200
    first = first_response.json()
    assert first["pension_contribution"] == "1200.50"
    assert first["donation_amount"] == "300.00"
    assert first["client_approved_at"] == "2026-02-15T12:00:00Z"
    assert first["internal_notes"] == "Initial review complete"
    assert first["updated_at"] is None
    assert "tax_refund_amount" not in first
    assert "tax_due_amount" not in first

    # Second patch should set updated_at
    follow_up = client.patch(
        f"/api/v1/annual-reports/{report.id}/details",
        headers=advisor_headers,
        json={"donation_amount": 450.25, "internal_notes": "Adjusted figures"},
    )

    assert follow_up.status_code == 200
    data = follow_up.json()
    assert data["donation_amount"] == "450.25"
    assert data["internal_notes"] == "Adjusted figures"
    assert data["updated_at"] is not None


def test_annual_report_detail_missing_report_returns_404(client, advisor_headers):
    response = client.get(
        "/api/v1/annual-reports/999/details",
        headers=advisor_headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANNUAL_REPORT.NOT_FOUND"

    patch_response = client.patch(
        "/api/v1/annual-reports/999/details",
        headers=advisor_headers,
        json={"donation_amount": 10},
    )
    assert patch_response.status_code == 404
    assert patch_response.json()["error"]["code"] == "ANNUAL_REPORT.NOT_FOUND"
