from app.annual_reports.services.annual_report_service import AnnualReportService


def test_client_and_tax_year_list_endpoints(
    client, test_db, advisor_headers, test_user, client_factory
):
    service = AnnualReportService(test_db)
    client_a = client_factory(full_name="Annual API Client 1", id_number="AAP001")
    client_b = client_factory(full_name="Annual API Client 2", id_number="AAP002")

    r1 = service.create_report(
        client_record_id=client_a.id,
        tax_year=2026,
        client_type="corporation",
        created_by=test_user.id,
        created_by_name="Test User",
    )
    r2 = service.create_report(
        client_record_id=client_a.id,
        tax_year=2025,
        client_type="corporation",
        created_by=test_user.id,
        created_by_name="Test User",
    )
    service.create_report(
        client_record_id=client_b.id,
        tax_year=2026,
        client_type="corporation",
        created_by=test_user.id,
        created_by_name="Test User",
    )

    client_reports = client.get(
        f"/api/v1/clients/{client_a.id}/annual-reports",
        headers=advisor_headers,
    )
    assert client_reports.status_code == 200
    assert [item["id"] for item in client_reports.json()["items"]] == [r1.id, r2.id]

    season_reports = client.get(
        "/api/v1/tax-year/2026/reports",
        headers=advisor_headers,
    )
    assert season_reports.status_code == 200
    data = season_reports.json()
    assert data["total"] == 2
    assert {item["tax_year"] for item in data["items"]} == {2026}


def test_active_season_endpoints_use_backend_tax_year(
    client, test_db, advisor_headers, test_user, monkeypatch, client_factory
):
    monkeypatch.setattr(
        "app.annual_reports.api.annual_report_routes_season.get_active_annual_report_tax_year",
        lambda: 2025,
    )
    service = AnnualReportService(test_db)
    client_a = client_factory(full_name="Annual API Client 1", id_number="AAP001")
    client_b = client_factory(full_name="Annual API Client 2", id_number="AAP002")

    service.create_report(
        client_record_id=client_a.id,
        tax_year=2025,
        client_type="corporation",
        created_by=test_user.id,
        created_by_name="Test User",
    )
    service.create_report(
        client_record_id=client_b.id,
        tax_year=2026,
        client_type="corporation",
        created_by=test_user.id,
        created_by_name="Test User",
    )

    summary = client.get("/api/v1/tax-year/active/summary", headers=advisor_headers)
    assert summary.status_code == 200
    assert summary.json()["tax_year"] == 2025
    assert summary.json()["filing_season_year"] == 2026

    reports = client.get("/api/v1/tax-year/active/reports", headers=advisor_headers)
    assert reports.status_code == 200
    assert reports.json()["total"] == 1
    assert {item["tax_year"] for item in reports.json()["items"]} == {2025}
