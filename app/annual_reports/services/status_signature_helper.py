"""Signature request helpers for annual report status transitions."""

from app.core.error_codes import ErrorCode
from app.annual_reports.services.base import AnnualReportBaseService
from app.annual_reports.services.messages import (
    ANNUAL_REPORT_APPROVAL_TITLE,
    ANNUAL_REPORT_CLIENT_NOT_FOUND,
    ANNUAL_REPORT_SIGNER_NAME_MISSING,
)
from app.core.exceptions import AppError, NotFoundError


class AnnualReportSignatureHelper(AnnualReportBaseService):
    """Mixin: manage signature requests during status transitions."""

    def _cancel_pending_signature_requests(
        self, report_id: int, actor_id: int, actor_name: str, reason: str
    ) -> None:
        from app.signature_requests.repositories.signature_request_repository import (
            SignatureRequestRepository,
        )
        from app.signature_requests.services.signature_request_service import (
            SignatureRequestService,
        )

        sig_repo = SignatureRequestRepository(self.db)
        pending = sig_repo.list_pending_by_annual_report(report_id)
        if not pending:
            return
        svc = SignatureRequestService(self.db)
        for req in pending:
            svc.cancel_request(
                client_record_id=req.client_record_id,
                request_id=req.id,
                canceled_by=actor_id,
                canceled_by_name=actor_name,
                reason=reason,
            )

    def _get_signature_client_context(self, report):
        record = self.client_repo.get_by_id(report.client_record_id)
        if not record:
            raise NotFoundError(
                ANNUAL_REPORT_CLIENT_NOT_FOUND.format(client_record_id=report.client_record_id),
                ErrorCode.CLIENT_RECORD_NOT_FOUND,
            )
        return record

    def _resolve_signer_name(self, record) -> str:
        name = self.client_repo.get_signer_name_by_legal_entity_id(
            record.legal_entity_id
        )
        if not name:
            raise AppError(
                ANNUAL_REPORT_SIGNER_NAME_MISSING,
                ErrorCode.ANNUAL_REPORT_SIGNER_NAME_MISSING,
            )
        return name

    def _trigger_signature_request(
        self, report, created_by: int, created_by_name: str, record
    ) -> None:
        from app.signature_requests.models.signature_request import SignatureRequestType
        from app.signature_requests.services.signature_request_service import (
            SignatureRequestService,
        )

        signer_name = self._resolve_signer_name(record)
        svc = SignatureRequestService(self.db)
        svc.create_request(
            client_record_id=report.client_record_id,
            business_id=None,
            created_by=created_by,
            created_by_name=created_by_name,
            request_type=SignatureRequestType.ANNUAL_REPORT_APPROVAL.value,
            title=ANNUAL_REPORT_APPROVAL_TITLE.format(tax_year=report.tax_year),
            signer_name=signer_name,
            annual_report_id=report.id,
            sent_by=created_by,
            sent_by_name=created_by_name,
            expiry_days=14,
        )
