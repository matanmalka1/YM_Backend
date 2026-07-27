import pytest
from sqlalchemy.exc import IntegrityError

from app.annual_reports.models.annual_report_enums import AnnualReportSchedule
from app.annual_reports.repositories.annual_report_schedule_repository import (
    AnnualReportScheduleRepository,
)


def test_schedule_repository_rejects_duplicate_schedule_per_report(test_db, annual_report_service_factory):
    report = annual_report_service_factory()
    repo = AnnualReportScheduleRepository(test_db)

    repo.add_schedule(report.id, AnnualReportSchedule.SCHEDULE_A)

    with pytest.raises(IntegrityError):
        repo.add_schedule(report.id, AnnualReportSchedule.SCHEDULE_A)

    test_db.rollback()
