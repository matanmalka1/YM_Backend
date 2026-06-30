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
from app.signature_requests.signature_request_audit import (
    ACTION_SIGNATURE_REQUEST_CANCELED,
    ACTION_SIGNATURE_REQUEST_EXPIRED,
    record_signature_system_action,
    record_signature_user_action,
)
from app.signature_requests.signature_request_messages import (
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
    canceled_by: int | None,
    canceled_by_name: str,
    reason: str | None = None,
    actor_type: str = "user",
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

    if actor_type == "system":
        record_signature_system_action(
            repo.db,
            req,
            action=ACTION_SIGNATURE_REQUEST_CANCELED,
            note=reason or CANCELED_BY_ADVISOR_NOTE,
            reason=reason,
        )
    else:
        if canceled_by is None:
            raise ValueError("canceled_by is required for user signature cancellation")
        record_signature_user_action(
            repo.db,
            req,
            actor_id=canceled_by,
            actor_display_name=canceled_by_name,
            action=ACTION_SIGNATURE_REQUEST_CANCELED,
            note=reason or CANCELED_BY_ADVISOR_NOTE,
            reason=reason,
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
        note = SIGNATURE_REQUEST_EXPIRED_NOTE.format(expires_at=req.expires_at.date().isoformat())
        record_signature_system_action(
            repo.db,
            req,
            action=ACTION_SIGNATURE_REQUEST_EXPIRED,
            note=note,
            reason=note,
        )
        count += 1
    return count
