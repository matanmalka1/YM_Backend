from app.annual_reports.services.annual_report_service import AnnualReportService


def test_delete_report_soft_deletes_existing_and_returns_false_for_missing(
    test_db, test_user, client_factory
):
    service = AnnualReportService(test_db)
    client = client_factory(full_name="Annual Delete Client", id_number="ADS001")
    report = service.create_report(
        client_record_id=client.id,
        tax_year=2026,
        client_type="corporation",
        created_by=test_user.id,
        created_by_name="Test User",
    )

    assert service.delete_report(report.id, actor_id=test_user.id, actor_name="Test User") is True
    assert service.repo.get_by_id(report.id) is None
    assert service.delete_report(999999, actor_id=test_user.id, actor_name="Test User") is False
