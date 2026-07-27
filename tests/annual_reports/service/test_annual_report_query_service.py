from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.services.annual_report_service import AnnualReportService


def _create_report(service: AnnualReportService, client_id: int, tax_year: int, created_by: int):
    return service.create_report(
        client_record_id=client_id,
        tax_year=tax_year,
        client_type="corporation",
        created_by=created_by,
        created_by_name="Test User",
        deadline_type="standard",
    )


def test_query_service_list_detail_and_client_reports(test_db, test_user, client_factory):
    service = AnnualReportService(test_db)
    client_a = client_factory(full_name="Annual Query Client 1", id_number="AQS001")
    client_b = client_factory(full_name="Annual Query Client 2", id_number="AQS002")

    report_a_2026 = _create_report(service, client_a.id, 2026, test_user.id)
    report_a_2025 = _create_report(service, client_a.id, 2025, test_user.id)
    report_b_2024 = _create_report(service, client_b.id, 2024, test_user.id)

    service.repo.update(report_a_2026.id, status=AnnualReportStatus.PENDING_CLIENT)
    service.repo.update(report_a_2025.id, status=AnnualReportStatus.SUBMITTED)
    service.repo.update(report_b_2024.id, status=AnnualReportStatus.IN_PREPARATION)

    client_reports, total_client_reports = service.get_client_reports(
        client_a.id, page=1, page_size=20
    )
    assert total_client_reports == 2
    assert [r.id for r in client_reports] == [report_a_2026.id, report_a_2025.id]
    # List rows are the thin AnnualReportListItem: no detail/calc/action fields.
    list_item = client_reports[0]
    for absent in (
        "schedules",
        "status_audit",
        "tax_calculation",
        "available_transitions",
        "notes",
        "created_by",
    ):
        assert not hasattr(list_item, absent)

    reports_2025, total_2025 = service.list_reports(tax_year=2025, page=1, page_size=20)
    assert total_2025 == 1
    assert [r.id for r in reports_2025] == [report_a_2025.id]
    assert reports_2025[0].is_overdue is False
    assert reports_2025[0].days_until_deadline is not None

    all_reports, total_all = service.list_reports(
        page=1, page_size=20, sort_by="tax_year", order="desc"
    )
    assert total_all == 3
    assert [r.id for r in all_reports] == [
        report_a_2026.id,
        report_a_2025.id,
        report_b_2024.id,
    ]

    detail = service.get_detail_report(report_a_2026.id)
    assert detail is not None
    assert detail.id == report_a_2026.id
    # Computed financial outputs are grouped under tax_calculation (item 36).
    assert detail.tax_calculation is not None
    assert detail.tax_calculation.total_income == 0.0
    assert detail.tax_calculation.total_expenses == 0.0
    assert detail.tax_calculation.credit_points_value == 6534.0
    assert detail.tax_calculation.donation_credit == 0.0
    # Removed duplicate float copies (item 35) are gone.
    assert not hasattr(detail, "tax_refund_amount")
    assert not hasattr(detail, "tax_due_amount")
    # Detail still carries detail-only + transition fields. Audit moved to the
    # generic /audit/annual_report/{id} endpoint.
    assert not hasattr(detail, "status_audit")
    assert hasattr(detail, "available_transitions")


def test_get_client_reports_empty_client_returns_empty_with_zero_total(test_db, client_factory):
    service = AnnualReportService(test_db)
    client = client_factory(full_name="Annual Query Client 1", id_number="AQS001")

    reports, total = service.get_client_reports(client.id, page=1, page_size=20)

    assert total == 0
    assert reports == []


def test_get_client_reports_deterministic_order_by_tax_year_desc(
    test_db, test_user, client_factory
):
    service = AnnualReportService(test_db)
    client = client_factory(full_name="Annual Query Client 1", id_number="AQS001")
    r_2024 = _create_report(service, client.id, 2024, test_user.id)
    r_2026 = _create_report(service, client.id, 2026, test_user.id)
    r_2025 = _create_report(service, client.id, 2025, test_user.id)

    reports, total = service.get_client_reports(client.id, page=1, page_size=20)

    assert total == 3
    # tax_year desc, with id desc as the stable tie-breaker.
    assert [r.id for r in reports] == [r_2026.id, r_2025.id, r_2024.id]
