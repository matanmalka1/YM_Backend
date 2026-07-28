from datetime import timedelta
from itertools import count

from app.annual_reports.repositories.annual_report_report_lifecycle_repository import (
    AnnualReportLifecycleRepository,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.common.enums import ObligationStatus
from app.utils.time_utils import utcnow
from tests.helpers.identity import seed_client_identity

_client_seq = count(1)


def _report(test_db, actor_id: int):
    idx = next(_client_seq)
    crm_client = seed_client_identity(
        test_db,
        full_name=f"Lifecycle Repo Extra {idx}",
        id_number=f"LRX{idx:03d}",
    )
    return AnnualReportService(test_db).create_report(
        client_record_id=crm_client.id,
        tax_year=2026,
        client_type="corporation",
        created_by=actor_id,
        created_by_name="Tester",
        deadline_type="standard",
    )


def test_lifecycle_soft_delete_true_and_false(test_db, user_factory):
    actor = user_factory(commit=False)
    repo = AnnualReportService(test_db).repo

    assert repo.soft_delete(999999, deleted_by=actor.id) is False

    report = _report(test_db, actor.id)
    assert repo.soft_delete(report.id, deleted_by=actor.id) is True

    refreshed = AnnualReportService(test_db).repo.get_by_client_record_year(
        report.client_record_id, 2026
    )
    assert refreshed is None


def test_list_for_dashboard_excludes_final_deleted_and_missing_deadline(test_db, user_factory):
    actor = user_factory(commit=False)
    service = AnnualReportService(test_db)
    open_report = _report(test_db, actor.id)
    submitted = _report(test_db, actor.id)
    no_deadline = _report(test_db, actor.id)
    deleted = _report(test_db, actor.id)

    service.repo.update(open_report.id, filing_deadline=utcnow() + timedelta(days=5))
    service.repo.update(
        submitted.id,
        status=ObligationStatus.SUBMITTED,
        filing_deadline=utcnow() + timedelta(days=1),
    )
    service.repo.update(no_deadline.id, filing_deadline=None)
    service.repo.soft_delete(deleted.id, deleted_by=actor.id)
    test_db.commit()

    lifecycle_repo = AnnualReportLifecycleRepository()
    lifecycle_repo.db = test_db
    result = lifecycle_repo.list_for_dashboard(limit=10)

    assert [report.id for report in result] == [open_report.id]
