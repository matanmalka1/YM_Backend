from itertools import count

from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.services.annual_report_service import AnnualReportService
from tests.helpers.identity import seed_client_identity

_client_seq = count(1)


def _client(db):
    idx = next(_client_seq)
    return seed_client_identity(
        db, full_name=f"Annual Query Client {idx}", id_number=f"AQS{idx:03d}"
    )


def _create_report(service: AnnualReportService, client_id: int, tax_year: int, created_by: int):
    return service.create_report(
        client_record_id=client_id,
        tax_year=tax_year,
        client_type="corporation",
        created_by=created_by,
        created_by_name="Test User",
        deadline_type="standard",
    )


def test_query_service_list_detail_and_client_reports(test_db, test_user):
    service = AnnualReportService(test_db)
    client_a = _client(test_db)
    client_b = _client(test_db)

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

    reports_2025, total_2025 = service.list_reports(tax_year=2025, page=1, page_size=20)
    assert total_2025 == 1
    assert [r.id for r in reports_2025] == [report_a_2025.id]

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
    assert detail.total_income == 0.0
    assert detail.total_expenses == 0.0
    assert len(detail.status_audit) >= 1
