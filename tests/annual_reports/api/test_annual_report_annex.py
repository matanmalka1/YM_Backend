def test_annex_crud_flow(client, advisor_headers, annual_report_service_factory):
    report = annual_report_service_factory()
    schedule = "schedule_b"

    create = client.post(
        f"/api/v1/annual-reports/{report.id}/annex/{schedule}",
        headers=advisor_headers,
        json={"data": {"rental_income": 12000}, "notes": "First line"},
    )
    assert create.status_code == 201
    line_id = create.json()["id"]
    assert create.json()["line_number"] == 1

    update = client.patch(
        f"/api/v1/annual-reports/{report.id}/annex/{schedule}/{line_id}",
        headers=advisor_headers,
        json={"data": {"rental_income": 15000}, "notes": "Updated"},
    )
    assert update.status_code == 200
    assert update.json()["data"]["rental_income"] == 15000

    listing = client.get(
        f"/api/v1/annual-reports/{report.id}/annex/{schedule}",
        headers=advisor_headers,
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert len(listing.json()["items"]) == 1

    delete = client.delete(
        f"/api/v1/annual-reports/{report.id}/annex/{schedule}/{line_id}",
        headers=advisor_headers,
    )
    assert delete.status_code == 204
    assert (
        client.get(
            f"/api/v1/annual-reports/{report.id}/annex/{schedule}",
            headers=advisor_headers,
        ).json()["items"]
        == []
    )


def test_add_annex_requires_report_exists(client, advisor_headers):
    resp = client.post(
        "/api/v1/annual-reports/999/annex/schedule_b",
        headers=advisor_headers,
        json={"data": {"rental_income": 1000}},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ANNUAL_REPORT.NOT_FOUND"
