from sqlalchemy.orm import Session

from app.annual_reports.repositories.annual_report_report_repository import (
    AnnualReportRootRepository,
)


class AnnualReportClientStatusService:
    def __init__(self, db: Session):
        self.repo = AnnualReportRootRepository(db)

    def cancel_open_by_client_record(self, client_record_id: int) -> int:
        return self.repo.cancel_open_by_client_record(client_record_id)
