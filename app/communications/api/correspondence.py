from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.communications.api.responses import (
    CORRESPONDENCE_CREATE_RESPONSES,
    CORRESPONDENCE_UPDATE_RESPONSES,
)
from app.communications.models.correspondence import CorrespondenceType
from app.communications.schemas.correspondence import (
    CorrespondenceCreateRequest,
    CorrespondenceListResponse,
    CorrespondenceResponse,
    CorrespondenceUpdateRequest,
)
from app.communications.services.correspondence_service import CorrespondenceService
from app.core.api_types import SortOrder
from app.core.openapi_responses import not_found_response
from app.core.pagination import MAX_PAGE_SIZE
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

_DEFAULT_PAGE_SIZE = 20

_AUTH = [Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))]
_ADVISOR_ONLY = [Depends(require_role(UserRole.ADVISOR))]

client_router = APIRouter(
    prefix="/clients",
    tags=["correspondence"],
    dependencies=_AUTH,
)


@client_router.get(
    "/{client_record_id}/correspondence",
    response_model=CorrespondenceListResponse,
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def list_correspondence_by_client(
    client_record_id: int,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    business_id: int | None = Query(None),
    correspondence_type: CorrespondenceType | None = Query(None),
    contact_id: int | None = Query(None),
    occurred_after: datetime | None = Query(None),
    occurred_before: datetime | None = Query(None),
    order: SortOrder = Query(SortOrder.desc),
):
    """All correspondence for a client, optionally filtered by business."""
    service = CorrespondenceService(db)
    entries, total = service.list_client_entries(
        client_record_id,
        page=page,
        page_size=page_size,
        business_id=business_id,
        correspondence_type=correspondence_type,
        contact_id=contact_id,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
        order=order,
    )
    return CorrespondenceListResponse.build(
        items=[CorrespondenceResponse.model_validate(e) for e in entries],
        page=page,
        page_size=page_size,
        total=total,
    )


@client_router.get(
    "/{client_record_id}/correspondence/{correspondence_id}",
    response_model=CorrespondenceResponse,
    responses=not_found_response(description="רשומת ההתכתבות המבוקשת לא נמצאה"),
)
def get_correspondence(
    client_record_id: int,
    correspondence_id: int,
    db: DBSession,
):
    entry = CorrespondenceService(db).get_entry(correspondence_id, client_record_id)
    return CorrespondenceResponse.model_validate(entry)


@client_router.post(
    "/{client_record_id}/correspondence",
    response_model=CorrespondenceResponse,
    status_code=status.HTTP_201_CREATED,
    responses=CORRESPONDENCE_CREATE_RESPONSES,
)
def create_correspondence(
    client_record_id: int,
    request: CorrespondenceCreateRequest,
    db: DBSession,
    user: CurrentUser,
):
    entry = CorrespondenceService(db).add_entry(
        client_record_id=client_record_id,
        business_id=request.business_id,
        correspondence_type=request.correspondence_type,
        subject=request.subject,
        occurred_at=request.occurred_at,
        created_by=user.id,
        contact_id=request.contact_id,
        notes=request.notes,
    )
    return CorrespondenceResponse.model_validate(entry)


@client_router.patch(
    "/{client_record_id}/correspondence/{correspondence_id}",
    response_model=CorrespondenceResponse,
    responses=CORRESPONDENCE_UPDATE_RESPONSES,
)
def update_correspondence(
    client_record_id: int,
    correspondence_id: int,
    request: CorrespondenceUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    entry = CorrespondenceService(db).update_entry(
        correspondence_id,
        client_record_id,
        **request.model_dump(exclude_unset=True),
    )
    return CorrespondenceResponse.model_validate(entry)


@client_router.delete(
    "/{client_record_id}/correspondence/{correspondence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_ADVISOR_ONLY,
    responses=not_found_response(description="רשומת ההתכתבות המבוקשת לא נמצאה"),
)
def delete_correspondence(
    client_record_id: int,
    correspondence_id: int,
    db: DBSession,
    user: CurrentUser,
):
    CorrespondenceService(db).delete_entry(correspondence_id, client_record_id, actor_id=user.id)
