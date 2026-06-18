from __future__ import annotations

from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.signature_requests.models.signature_request import (
    SignatureRequest,
    SignatureRequestStatus,
)
from app.signature_requests.repositories.signature_request_repository import (
    SignatureRequestRepository,
)
from app.signature_requests.services.messages import (
    CANCELED_BY_ADVISOR_NOTE,
    SIGNATURE_REQUEST_EXPIRED_NOTE,
    SIGNATURE_REQUEST_NOT_FOUND,
)
from app.utils.time_utils import utcnow


def cancel_request(
    repo: SignatureRequestRepository,
    *,
    client_record_id: int,
    request_id: int,
    canceled_by: int,
    canceled_by_name: str,
    reason: str | None = None,
) -> SignatureRequest:
    req = repo.get_pending_by_client_and_id_for_update(client_record_id, request_id)
    if not req:
        raise NotFoundError(
            SIGNATURE_REQUEST_NOT_FOUND.format(request_id=request_id),
            ErrorCode.SIGNATURE_REQUEST_NOT_FOUND,
        )

    req = repo.update(
        request_id,
        req=req,
        status=SignatureRequestStatus.CANCELED,
        canceled_at=utcnow(),
        canceled_by=canceled_by,
        signing_token=None,
    )

    repo.append_audit_event(
        signature_request_id=request_id,
        event_type="canceled",
        actor_type="advisor",
        actor_id=canceled_by,
        actor_name=canceled_by_name,
        notes=reason or CANCELED_BY_ADVISOR_NOTE,
    )

    return req


def expire_overdue_requests(repo: SignatureRequestRepository) -> int:
    """Mark expired pending requests and return count."""
    expired_reqs = repo.list_expired_pending()
    count = 0
    for req in expired_reqs:
        repo.update(
            req.id,
            req=req,
            status=SignatureRequestStatus.EXPIRED,
            signing_token=None,
        )
        repo.append_audit_event(
            signature_request_id=req.id,
            event_type="expired",
            actor_type="system",
            notes=SIGNATURE_REQUEST_EXPIRED_NOTE.format(
                expires_at=req.expires_at.date().isoformat()
            ),
        )
        count += 1
    return count
