def test_transition_stage_success_and_not_found(client, advisor_headers, annual_report_service_factory):
    report_id = annual_report_service_factory().id

    ok = client.post(
        f"/api/v1/annual-reports/{report_id}/transition",
        headers=advisor_headers,
        json={"to_stage": "material_collection"},
    )
    assert ok.status_code == 200

    missing = client.post(
        "/api/v1/annual-reports/999999/transition",
        headers=advisor_headers,
        json={"to_stage": "material_collection"},
    )
    assert missing.status_code == 404
