from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.audit.audit_constants import ENTITY_SIGNATURE_REQUEST
from app.audit.services.audit_trail_service import AuditTrailService
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
    signature_request_admin_service as admin_actions,
)
from app.signature_requests.services import (
    signature_request_creation_service as create_request,
)
from app.signature_requests.services import (
    signature_request_signer_service as signer_actions,
)
from app.signature_requests.signature_request_messages import INVALID_FILTER_STATUS
from app.signature_requests.signature_request_validations import get_or_raise


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
        return signer_actions.sign_request(self.repo, **kwargs)

    def decline_request(self, **kwargs):
        return signer_actions.decline_request(self.repo, **kwargs)

    # ── Advisor / system actions ──────────────────────────────────────────────

    def cancel_request(
        self,
        *,
        client_record_id: int,
        request_id: int,
        canceled_by: int | None,
        canceled_by_name: str,
        reason: str | None = None,
        actor_type: str = "user",
    ) -> SignatureRequest:
        return admin_actions.cancel_request(
            self.repo,
            client_record_id=client_record_id,
            request_id=request_id,
            canceled_by=canceled_by,
            canceled_by_name=canceled_by_name,
            reason=reason,
            actor_type=actor_type,
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

    def get_audit_trail(self, request_id: int, *, current_user) -> list:
        get_or_raise(self.repo, request_id)
        return AuditTrailService(self.db).get_entity_audit_items(
            ENTITY_SIGNATURE_REQUEST,
            request_id,
            current_user=current_user,
        )

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
