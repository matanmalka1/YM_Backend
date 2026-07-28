from app.audit.audit_constants import ACTION_STATUS_CHANGED, ENTITY_ANNUAL_REPORT, entity_action

STATUS_CHANGED = entity_action(ENTITY_ANNUAL_REPORT, ACTION_STATUS_CHANGED)


def _transition_to_collecting_docs(client, advisor_headers, report_id: int) -> None:
    """Advance one stage off awaiting_input.

    This used to move not_started -> collecting_docs. Those merged into one stage,
    so the first real move is now to input_received.
    """
    resp = client.post(
        f"/api/v1/annual-reports/{report_id}/status",
        headers=advisor_headers,
        json={"status": "input_received", "note": "Started collection"},
    )
    assert resp.status_code == 200


def test_generic_annual_report_audit_returns_status_entries(
    client, advisor_headers, test_user, annual_report_service_factory
):
    report = annual_report_service_factory(actor=test_user)
    _transition_to_collecting_docs(client, advisor_headers, report.id)

    resp = client.get(
        f"/api/v1/audit/annual_report/{report.id}?action={STATUS_CHANGED}",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["page"] == 1
    assert payload["page_size"] == 20
    item = payload["items"][0]
    assert item["entity_type"] == "annual_report"
    assert item["entity_id"] == report.id
    assert item["action"] == "annual_report.status_changed"
    assert item["old_value"] == {"status": "awaiting_input"}
    assert item["new_value"] == {"status": "awaiting_input"}
    assert item["metadata_json"] == {
        "client_record_id": report.client_record_id,
        "tax_year": report.tax_year,
    }
    assert item["note"] == "Started collection"
    assert item["performed_by"] == test_user.id
    assert item["actor_display_name"] == test_user.full_name


def test_generic_annual_report_audit_is_readable_by_secretary(
    client, advisor_headers, secretary_headers, test_user, annual_report_service_factory
):
    report = annual_report_service_factory(actor=test_user)
    _transition_to_collecting_docs(client, advisor_headers, report.id)

    resp = client.get(f"/api/v1/audit/annual_report/{report.id}", headers=secretary_headers)

    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


def test_generic_annual_report_audit_404_when_missing(client, advisor_headers):
    resp = client.get("/api/v1/audit/annual_report/999999", headers=advisor_headers)

    assert resp.status_code == 404


def test_annual_report_legacy_audit_route_is_removed(
    client, advisor_headers, test_user, annual_report_service_factory
):
    report_id = annual_report_service_factory(actor=test_user).id

    resp = client.get(f"/api/v1/annual-reports/{report_id}/audit", headers=advisor_headers)

    assert resp.status_code == 404
