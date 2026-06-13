from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.core.openapi_responses import not_found_response
from app.core.pagination import MAX_PAGE_SIZE
from app.signature_requests.api.responses import SIGNATURE_CREATE_RESPONSES
from app.signature_requests.schemas.signature_request import (
    SignatureRequestCreatedResponse,
    SignatureRequestCreateRequest,
    SignatureRequestListResponse,
    SignatureRequestWithAuditResponse,
)
from app.signature_requests.services.response_builder import (
    SignatureRequestResponseBuilder,
)
from app.signature_requests.services.signature_request_service import (
    SignatureRequestService,
)
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

advisor_router = APIRouter(
    prefix="/signature-requests",
    tags=["signature-requests"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@advisor_router.post(
    "",
    response_model=SignatureRequestCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    responses=SIGNATURE_CREATE_RESPONSES,
)
def create_signature_request(
    request: SignatureRequestCreateRequest,
    db: DBSession,
    user: CurrentUser,
):
    service = SignatureRequestService(db)
    req = service.create_request(
        client_record_id=request.client_record_id,
        business_id=request.business_id,
        created_by=user.id,
        created_by_name=user.full_name,
        request_type=request.request_type,
        title=request.title,
        description=request.description,
        signer_name=request.signer_name,
        signer_email=request.signer_email,
        signer_phone=request.signer_phone,
        annual_report_id=request.annual_report_id,
        document_id=request.document_id,
        content_to_hash=request.content_to_hash,
        sent_by=user.id,
        sent_by_name=user.full_name,
        expiry_days=request.expiry_days,
    )
    return SignatureRequestResponseBuilder(db).build_created(req)


@advisor_router.get("/pending", response_model=SignatureRequestListResponse)
def list_pending_requests(
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    service = SignatureRequestService(db)
    items, total = service.list_pending_requests(page=page, page_size=page_size)
    return SignatureRequestResponseBuilder(db).build_list(
        items,
        total,
        page=page,
        page_size=page_size,
    )


@advisor_router.get(
    "/{request_id}",
    response_model=SignatureRequestWithAuditResponse,
    responses=not_found_response(description="בקשת החתימה המבוקשת לא נמצאה"),
)
def get_signature_request(request_id: int, db: DBSession, user: CurrentUser):
    service = SignatureRequestService(db)
    req = service.get_request(request_id)
    audit_events = service.get_audit_trail(request_id)
    return SignatureRequestResponseBuilder(db).build_with_audit(req, audit_events)
