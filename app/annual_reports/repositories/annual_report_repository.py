"""Domain repository facade for annual-report repository operations.

AnnualReportRepository intentionally composes the lower-level repository classes used
by the annual-reports domain. AnnualReportRootRepository owns DB access for the
AnnualReport aggregate root row.
"""

from sqlalchemy.orm import Session

from app.annual_reports.repositories.annual_report_report_lifecycle_repository import (
    AnnualReportLifecycleRepository,
)
from app.annual_reports.repositories.annual_report_report_repository import (
    AnnualReportRootRepository,
)
from app.annual_reports.repositories.annual_report_schedule_repository import (
    AnnualReportScheduleRepository,
)


class AnnualReportRepository(
    AnnualReportRootRepository,
    AnnualReportLifecycleRepository,
    AnnualReportScheduleRepository,
):
    def __init__(self, db: Session):
        # Each mixin expects self.db
        self.db = db


__all__ = ["AnnualReportRepository"]
