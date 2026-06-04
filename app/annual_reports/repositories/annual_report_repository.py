"""Domain repository facade for annual-report repository operations.

AnnualReportRepository intentionally composes the lower-level repository classes used
by the annual-reports domain. AnnualReportRootRepository owns DB access for the
AnnualReport aggregate root row.
"""

from sqlalchemy.orm import Session

from app.annual_reports.repositories.report_lifecycle_repository import (
    AnnualReportLifecycleRepository,
)
from app.annual_reports.repositories.report_repository import (
    AnnualReportRootRepository,
)
from app.annual_reports.repositories.schedule_repository import (
    AnnualReportScheduleRepository,
)
from app.annual_reports.repositories.status_history_repository import (
    AnnualReportStatusHistoryRepository,
)


class AnnualReportRepository(
    AnnualReportRootRepository,
    AnnualReportLifecycleRepository,
    AnnualReportScheduleRepository,
    AnnualReportStatusHistoryRepository,
):
    def __init__(self, db: Session):
        # Each mixin expects self.db
        self.db = db


__all__ = ["AnnualReportRepository"]
