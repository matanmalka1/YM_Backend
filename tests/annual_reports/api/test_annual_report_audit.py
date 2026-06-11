from app.annual_reports.services.annual_report_service import AnnualReportService
from tests.helpers.identity import seed_client_identity


def _create_report(db, user_id: int) -> int:
    crm_client = seed_client_identity(db, full_name="AR Audit Client", id_number="ARAUD001")

    report = AnnualReportService(db).create_report(
        client_record_id=crm_client.id,
        tax_year=2026,
        client_type="corporation",
        created_by=user_id,
        created_by_name="Audit Tester",
        deadline_type="standard",
        notes=None,
    )
    return report.id


def test_annual_report_audit_endpoint_returns_status_entries(
    client, test_db, advisor_headers, test_user
):
    report_id = _create_report(test_db, test_user.id)

    resp = client.get(f"/api/v1/annual-reports/{report_id}/audit", headers=advisor_headers)

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] >= 1
    assert payload["page"] == 1
    assert payload["page_size"] == 50
    assert payload["items"][0]["annual_report_id"] == report_id
    assert payload["items"][0]["to_status"] == "not_started"


def test_annual_report_audit_404_when_missing(client, advisor_headers):
    resp = client.get("/api/v1/annual-reports/999999/audit", headers=advisor_headers)

    assert resp.status_code == 404


def test_annual_report_history_endpoint_is_removed(client, test_db, advisor_headers, test_user):
    report_id = _create_report(test_db, test_user.id)

    resp = client.get(f"/api/v1/annual-reports/{report_id}/history", headers=advisor_headers)

    assert resp.status_code == 404
