def test_get_schedules_returns_entries_for_report(client, advisor_headers, annual_report_factory):
    report_id = annual_report_factory().id

    create_resp = client.post(
        f"/api/v1/annual-reports/{report_id}/schedules",
        headers=advisor_headers,
        json={"schedule": "schedule_b", "notes": "First schedule"},
    )
    assert create_resp.status_code == 201

    resp = client.get(
        f"/api/v1/annual-reports/{report_id}/schedules",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert isinstance(body["items"], list)
    assert any(item["schedule"] == "schedule_b" for item in body["items"])
    assert all(item["annual_report_id"] == report_id for item in body["items"])


def test_get_schedules_returns_404_for_missing_report(client, advisor_headers):
    resp = client.get(
        "/api/v1/annual-reports/999999/schedules",
        headers=advisor_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ANNUAL_REPORT.NOT_FOUND"


def test_schedule_invalid_type_and_complete_missing_schedule(
    client, advisor_headers, annual_report_factory
):
    report_id = annual_report_factory().id

    invalid = client.post(
        f"/api/v1/annual-reports/{report_id}/schedules",
        headers=advisor_headers,
        json={"schedule": "invalid_schedule"},
    )
    assert invalid.status_code == 422

    missing = client.post(
        f"/api/v1/annual-reports/{report_id}/schedules/complete",
        headers=advisor_headers,
        json={"schedule": "schedule_b"},
    )
    assert missing.status_code == 404
