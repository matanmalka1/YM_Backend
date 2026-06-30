from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.services.annual_report_service import AnnualReportService


def _force_submitted(db, report_id: int):
    AnnualReportService(db).repo.update(report_id, status=AnnualReportStatus.SUBMITTED)


def test_annual_report_overdue_endpoint(
    client, advisor_headers, test_user, client_factory, annual_report_factory
):
    old_client = client_factory()
    new_client = client_factory()

    annual_report_factory(actor=test_user, client=old_client, tax_year=2020)
    annual_report_factory(actor=test_user, client=new_client, tax_year=2099)

    resp = client.get("/api/v1/annual-reports/overdue", headers=advisor_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] >= 1
    overdue_ids = {item.get("business_id", item.get("client_record_id")) for item in body["items"]}
    assert old_client.id in overdue_ids
    assert new_client.id not in overdue_ids


def test_annual_report_amend_endpoint(
    client, test_db, advisor_headers, test_user, client_factory, annual_report_factory
):
    crm_client = client_factory()
    report_id = annual_report_factory(actor=test_user, client=crm_client).id
    _force_submitted(test_db, report_id)

    amend_resp = client.post(
        f"/api/v1/annual-reports/{report_id}/amend",
        headers=advisor_headers,
        json={"reason": "Correction requested"},
    )

    assert amend_resp.status_code == 200
    body = amend_resp.json()
    assert body["status"] == "in_preparation"
    assert body["amendment_reason"] == "Correction requested"


def test_annual_report_schedule_complete_and_season_summary(
    client,
    test_db,
    advisor_headers,
    test_user,
    client_factory,
    annual_report_factory,
):
    c1 = client_factory()
    c2 = client_factory()

    report_id = annual_report_factory(actor=test_user, client=c1).id
    completed_report_id = annual_report_factory(actor=test_user, client=c2).id

    add_schedule_resp = client.post(
        f"/api/v1/annual-reports/{report_id}/schedules",
        headers=advisor_headers,
        json={"schedule": "schedule_b", "notes": "required"},
    )
    assert add_schedule_resp.status_code == 201

    complete_schedule_resp = client.post(
        f"/api/v1/annual-reports/{report_id}/schedules/complete",
        headers=advisor_headers,
        json={"schedule": "schedule_b"},
    )
    assert complete_schedule_resp.status_code == 200
    assert complete_schedule_resp.json()["is_complete"] is True

    _force_submitted(test_db, completed_report_id)

    summary_resp = client.get("/api/v1/tax-year/2026/summary", headers=advisor_headers)
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["tax_year"] == 2026
    assert summary["total"] >= 2
    assert summary["submitted"] >= 1
