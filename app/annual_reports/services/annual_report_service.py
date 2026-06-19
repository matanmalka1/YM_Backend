from sqlalchemy.orm import Session

from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.annual_reports.repositories.annual_report_annex_data_repository import AnnexDataRepository
from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.audit.audit_constants import ENTITY_ANNUAL_REPORT
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.businesses.repositories.business_repository import BusinessRepository
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.users.repositories.user_repository import UserRepository
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)

from ..annual_report_messages import ANNUAL_REPORT_DELETED_REASON, ANNUAL_REPORT_NOT_FOUND
from .annual_report_annex_service import AnnualReportAnnexService
from .annual_report_create_service import AnnualReportCreateService
from .annual_report_query_service import AnnualReportQueryService
from .annual_report_schedule_service import AnnualReportScheduleService
from .annual_report_season_service import AnnualReportSeasonService
from .annual_report_status_service import AnnualReportStatusService


class AnnualReportService(
    AnnualReportCreateService,
    AnnualReportStatusService,
    AnnualReportSeasonService,
    AnnualReportScheduleService,
    AnnualReportQueryService,
    AnnualReportAnnexService,
):
    """Facade combining annual report operations."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = AnnualReportRepository(db)
        self.annex_repo = AnnexDataRepository(db)
        # Cross-domain repositories are wired only at facade level (service boundary).
        # Lower annual_reports service mixins must consume these via self.<repo_name> only.
        self.business_repo = BusinessRepository(db)
        self.user_repo = UserRepository(db)
        self.client_repo = ClientRecordRepository(db)
        self.vat_repo = VatWorkItemRepository(db)
        self.advance_repo = AdvancePaymentRepository(db)

    def assert_report_exists(self, report_id: int) -> None:
        """Raise NotFoundError if the report does not exist."""
        if not self.repo.get_by_id(report_id):
            raise NotFoundError(
                ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
                ErrorCode.ANNUAL_REPORT_NOT_FOUND,
            )

    def delete_report(self, report_id: int, actor_id: int, actor_name: str) -> bool:
        """Soft-delete an annual report. Returns False if not found."""
        report = self.repo.get_by_id(report_id)
        if not report:
            return False
        self._cancel_pending_signature_requests(
            report_id, actor_id, actor_name, ANNUAL_REPORT_DELETED_REASON
        )
        result = self.repo.soft_delete(report_id, deleted_by=actor_id)
        if result:
            EntityAuditWriter(self.db).record_delete(ENTITY_ANNUAL_REPORT, report_id, actor_id)
        return result


__all__ = ["AnnualReportService"]
