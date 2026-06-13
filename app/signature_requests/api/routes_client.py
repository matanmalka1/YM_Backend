from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.openapi_responses import not_found_response
from app.core.pagination import MAX_PAGE_SIZE
from app.signature_requests.api.responses import SIGNATURE_CANCEL_RESPONSES
from app.signature_requests.schemas.signature_request import (
    CancelRequest,
    SignatureRequestListResponse,
    SignatureRequestResponse,
)
from app.signature_requests.services.response_builder import SignatureRequestResponseBuilder
from app.signature_requests.services.signature_request_service import (
    SignatureRequestService,
)
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

client_router = APIRouter(
    tags=["signature-requests"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@client_router.post(
    "/clients/{client_record_id}/signature-requests/{request_id}/cancel",
    response_model=SignatureRequestResponse,
    responses=SIGNATURE_CANCEL_RESPONSES,
)
def cancel_client_signature_request(
    client_record_id: int,
    request_id: int,
    body: CancelRequest,
    db: DBSession,
    user: CurrentUser,
):
    req = SignatureRequestService(db).cancel_request(
        client_record_id=client_record_id,
        request_id=request_id,
        canceled_by=user.id,
        canceled_by_name=user.full_name,
        reason=body.reason,
    )
    return SignatureRequestResponseBuilder(db).build(req)


@client_router.get(
    "/clients/{client_record_id}/signature-requests",
    response_model=SignatureRequestListResponse,
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def list_client_signature_requests(
    client_record_id: int,
    db: DBSession,
    user: CurrentUser,
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    """All signature requests for a legal entity, across all businesses."""
    service = SignatureRequestService(db)
    items, total = service.list_client_requests(
        client_record_id=client_record_id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    office_number_map = {
        record.id: record.office_client_number
        for record in ClientRecordRepository(db).list_by_ids(
            sorted({item.client_record_id for item in items})
        )
    }
    return SignatureRequestListResponse(
        items=[
            SignatureRequestResponse.model_validate(r).model_copy(
                update={"office_client_number": office_number_map.get(r.client_record_id)}
            )
            for r in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )
