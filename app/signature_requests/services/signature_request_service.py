from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.businesses.repositories.business_repository import BusinessRepository
from app.clients.services.client_service import get_client_or_raise
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError
from app.signature_requests.models.signature_request import (
    SignatureRequest,
    SignatureRequestStatus,
    SignatureRequestType,
)
from app.signature_requests.repositories.signature_request_repository import (
    SignatureRequestRepository,
)
from app.signature_requests.services import (
    admin_actions,
    create_request,
    signer_actions,
)
from app.signature_requests.services.messages import (
    ANNUAL_REPORT_SIGNED_NOTE,
    AUTO_ADVANCE_ANNUAL_REPORT_ERROR,
    AUTO_SUBMITTED_AFTER_SIGNATURE_NOTE,
    INVALID_FILTER_STATUS,
    SYSTEM_USER_NAME,
)
from app.signature_requests.services.signature_request_validations import get_or_raise

_log = logging.getLogger(__name__)

_SYSTEM_USER_ID = 0
_SYSTEM_USER_NAME = SYSTEM_USER_NAME


class SignatureRequestService:
    """Orchestrates digital signature request lifecycle."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = SignatureRequestRepository(db)
        self.business_repo = BusinessRepository(db)

    # ── Create ────────────────────────────────────────────────────────────────

    def create_request(
        self,
        *,
        sent_by: int,
        sent_by_name: str,
        expiry_days: int,
        **create_kwargs,
    ):
        return create_request.create_request(
            self.repo,
            self.business_repo,
            sent_by=sent_by,
            sent_by_name=sent_by_name,
            expiry_days=expiry_days,
            **create_kwargs,
        )

    # ── Signer actions ────────────────────────────────────────────────────────

    def record_view(self, **kwargs):
        return signer_actions.record_view(self.repo, **kwargs)

    def sign_request(self, **kwargs):
        req, annual_report_id, signed_at = signer_actions.sign_request(self.repo, **kwargs)
        if annual_report_id:
            self.repo.append_audit_event(
                signature_request_id=req.id,
                event_type="annual_report_signed",
                actor_type="system",
                notes=ANNUAL_REPORT_SIGNED_NOTE.format(annual_report_id=annual_report_id),
            )
            self._auto_advance_annual_report(annual_report_id, signed_at)
        return req

    def decline_request(self, **kwargs):
        return signer_actions.decline_request(self.repo, **kwargs)

    def _auto_advance_annual_report(self, annual_report_id: int, now) -> None:
        try:
            from app.annual_reports.models.annual_report_enums import AnnualReportStatus
            from app.annual_reports.repositories.detail_repository import (
                AnnualReportDetailRepository,
            )
            from app.annual_reports.services.annual_report_service import (
                AnnualReportService,
            )

            svc = AnnualReportService(self.db)
            report = svc.repo.get_by_id(annual_report_id)
            if report is None or report.status != AnnualReportStatus.PENDING_CLIENT:
                return
            svc.transition_status(
                report_id=annual_report_id,
                new_status=AnnualReportStatus.SUBMITTED.value,
                changed_by=_SYSTEM_USER_ID,
                changed_by_name=_SYSTEM_USER_NAME,
                note=AUTO_SUBMITTED_AFTER_SIGNATURE_NOTE,
            )
            detail_repo = AnnualReportDetailRepository(self.db)
            detail_repo.update_meta(annual_report_id, client_approved_at=now)
        except Exception:
            _log.exception(AUTO_ADVANCE_ANNUAL_REPORT_ERROR, annual_report_id)

    # ── Advisor / system actions ──────────────────────────────────────────────

    def cancel_request(
        self,
        *,
        client_record_id: int,
        request_id: int,
        canceled_by: int,
        canceled_by_name: str,
        reason: str | None = None,
    ) -> SignatureRequest:
        return admin_actions.cancel_request(
            self.repo,
            client_record_id=client_record_id,
            request_id=request_id,
            canceled_by=canceled_by,
            canceled_by_name=canceled_by_name,
            reason=reason,
        )

    def expire_overdue_requests(self):
        return admin_actions.expire_overdue_requests(self.repo)

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_request(self, request_id: int) -> SignatureRequest:
        return get_or_raise(self.repo, request_id)

    def get_by_token(self, token: str) -> SignatureRequest | None:
        return self.repo.get_by_token(token)

    def list_client_requests(
        self,
        *,
        client_record_id: int,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SignatureRequest], int]:
        status_enum = self._parse_status(status)
        get_client_or_raise(self.db, client_record_id)
        items = self.repo.list_by_client_record(
            client_record_id, status=status_enum, page=page, page_size=page_size
        )
        total = self.repo.count_by_client_record(client_record_id, status=status_enum)
        return items, total

    def list_pending_requests(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        client_record_id: int | None = None,
        request_type: SignatureRequestType | None = None,
        signer_email: str | None = None,
        created_after: date | None = None,
        created_before: date | None = None,
        expires_before: date | None = None,
    ) -> tuple[list[SignatureRequest], int]:
        filters = {
            "client_record_id": client_record_id,
            "request_type": request_type,
            "signer_email": signer_email,
            "created_after": created_after,
            "created_before": created_before,
            "expires_before": expires_before,
        }
        items = self.repo.list_pending(page=page, page_size=page_size, **filters)
        total = self.repo.count_pending(**filters)
        return items, total

    def get_audit_trail(self, request_id: int) -> list:
        get_or_raise(self.repo, request_id)
        return self.repo.list_audit_events(request_id)

    @staticmethod
    def _parse_status(status: str | None) -> SignatureRequestStatus | None:
        if not status:
            return None
        valid_statuses = {e.value for e in SignatureRequestStatus}
        if status not in valid_statuses:
            raise AppError(
                INVALID_FILTER_STATUS.format(status=status, valid_statuses=sorted(valid_statuses)),
                ErrorCode.SIGNATURE_REQUEST_INVALID_STATUS,
            )
        return SignatureRequestStatus(status)
