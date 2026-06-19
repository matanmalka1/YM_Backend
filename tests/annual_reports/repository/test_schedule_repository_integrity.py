import pytest
from sqlalchemy.exc import IntegrityError

from app.annual_reports.models.annual_report_enums import AnnualReportSchedule
from app.annual_reports.repositories.annual_report_schedule_repository import (
    AnnualReportScheduleRepository,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from tests.helpers.identity import seed_client_identity


def _create_report(db):
    crm_client = seed_client_identity(db, full_name="AR Schedule Integrity", id_number="ARSCHED001")

    return AnnualReportService(db).create_report(
        client_record_id=crm_client.id,
        tax_year=2026,
        client_type="corporation",
        created_by=1,
        created_by_name="Tester",
        deadline_type="standard",
    )


def test_schedule_repository_rejects_duplicate_schedule_per_report(test_db):
    report = _create_report(test_db)
    repo = AnnualReportScheduleRepository(test_db)

    repo.add_schedule(report.id, AnnualReportSchedule.SCHEDULE_A)

    with pytest.raises(IntegrityError):
        repo.add_schedule(report.id, AnnualReportSchedule.SCHEDULE_A)

    test_db.rollback()
