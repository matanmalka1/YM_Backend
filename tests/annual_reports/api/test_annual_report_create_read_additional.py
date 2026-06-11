from app.annual_reports.services.annual_report_service import AnnualReportService
from tests.helpers.identity import seed_client_identity


def _create_report(db) -> int:
    crm_client = seed_client_identity(
        db, full_name="AR CreateRead Additional", id_number="ARCRA001"
    )

    report = AnnualReportService(db).create_report(
        client_record_id=crm_client.id,
        tax_year=2026,
        client_type="corporation",
        created_by=1,
        created_by_name="Tester",
        deadline_type="standard",
        notes=None,
    )
    return report.id


def test_get_report_not_found_and_delete_paths(client, test_db, advisor_headers):
    missing = client.get("/api/v1/annual-reports/999999", headers=advisor_headers)
    assert missing.status_code == 404

    report_id = _create_report(test_db)
    get_ok = client.get(f"/api/v1/annual-reports/{report_id}", headers=advisor_headers)
    assert get_ok.status_code == 200
    body = get_ok.json()
    assert body["client_record_id"] is not None
    assert body["client_name"] == "AR CreateRead Additional"
    assert body["available_transitions"] == ["collecting_docs"]

    del_ok = client.delete(f"/api/v1/annual-reports/{report_id}", headers=advisor_headers)
    assert del_ok.status_code == 204

    del_missing = client.delete("/api/v1/annual-reports/999999", headers=advisor_headers)
    assert del_missing.status_code == 404


def test_list_dto_thin_while_detail_dto_full(client, test_db, advisor_headers):
    """Regression guard for the list/detail DTO split (items 35-37).

    GET /annual-reports rows must be the thin AnnualReportListItem (no
    detail/calc/action fields); GET /annual-reports/{id} must keep the full
    detail shape with grouped tax_calculation and no duplicate *_amount fields.
    """
    report_id = _create_report(test_db)

    list_resp = client.get("/api/v1/annual-reports", headers=advisor_headers)
    assert list_resp.status_code == 200
    row = next(r for r in list_resp.json()["items"] if r["id"] == report_id)
    # Thin row carries identity/status/outcome only.
    assert row["client_name"] == "AR CreateRead Additional"
    assert {"tax_year", "status", "assessment_amount", "refund_due", "tax_due"} <= row.keys()
    # Heavy detail/calc/action fields must NOT appear in list rows.
    for absent in (
        "schedules",
        "status_audit",
        "tax_calculation",
        "available_actions",
        "available_transitions",
        "notes",
        "business_name",
        "created_by",
        "tax_refund_amount",
        "tax_due_amount",
    ):
        assert absent not in row

    detail = client.get(f"/api/v1/annual-reports/{report_id}", headers=advisor_headers).json()
    # Detail keeps full shape with grouped calculation + actions/transitions.
    assert "tax_calculation" in detail
    assert {
        "total_income",
        "taxable_income",
        "final_balance",
        "credit_points",
    } <= detail["tax_calculation"].keys()
    assert "available_actions" in detail
    assert "available_transitions" in detail
    # Removed duplicate float copies (item 35) are gone from detail.
    assert "tax_refund_amount" not in detail
    assert "tax_due_amount" not in detail
