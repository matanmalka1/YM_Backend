def test_annual_report_audit_endpoint_returns_status_entries(
    client, advisor_headers, test_user, annual_report_factory
):
    report_id = annual_report_factory(actor=test_user).id

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


def test_annual_report_history_endpoint_is_removed(
    client, advisor_headers, test_user, annual_report_factory
):
    report_id = annual_report_factory(actor=test_user).id

    resp = client.get(f"/api/v1/annual-reports/{report_id}/history", headers=advisor_headers)

    assert resp.status_code == 404
