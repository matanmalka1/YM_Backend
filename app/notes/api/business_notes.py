from fastapi import APIRouter, Depends, Query, Response, status

from app.core.openapi_responses import not_found_response
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.notes.api.responses import BUSINESS_NOTE_CREATE_RESPONSES, NOTE_UPDATE_RESPONSES
from app.notes.schemas.entity_note import (
    EntityNoteCreateRequest,
    EntityNoteListResponse,
    EntityNoteResponse,
    EntityNoteUpdateRequest,
)
from app.notes.services.business_note_service import BusinessNoteService
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/clients/{client_record_id}/businesses/{business_id}/notes",
    tags=["notes"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get(
    "",
    response_model=EntityNoteListResponse,
    responses=not_found_response(description="העסק המבוקש לא נמצא"),
)
def list_notes(
    client_record_id: int,
    business_id: int,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    items, total = BusinessNoteService(db).list_notes(
        client_id=client_record_id,
        business_id=business_id,
        page=page,
        page_size=page_size,
    )
    return EntityNoteListResponse(
        items=[EntityNoteResponse.model_validate(n) for n in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "",
    response_model=EntityNoteResponse,
    status_code=status.HTTP_201_CREATED,
    responses=BUSINESS_NOTE_CREATE_RESPONSES,
)
def add_note(
    client_record_id: int,
    business_id: int,
    request: EntityNoteCreateRequest,
    db: DBSession,
    user: CurrentUser,
):
    note = BusinessNoteService(db).add_note(
        client_id=client_record_id,
        business_id=business_id,
        note=request.note,
        created_by=user.id,
    )
    return EntityNoteResponse.model_validate(note)


@router.patch(
    "/{note_id}",
    response_model=EntityNoteResponse,
    responses=NOTE_UPDATE_RESPONSES,
)
def update_note(
    client_record_id: int,
    business_id: int,
    note_id: int,
    request: EntityNoteUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    note = BusinessNoteService(db).update_note(
        client_id=client_record_id,
        business_id=business_id,
        note_id=note_id,
        note=request.note,
        actor_id=user.id,
    )
    return EntityNoteResponse.model_validate(note)


@router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=not_found_response(description="ההערה המבוקשת לא נמצאה"),
)
def delete_note(
    client_record_id: int,
    business_id: int,
    note_id: int,
    db: DBSession,
    user: CurrentUser,
):
    BusinessNoteService(db).delete_note(
        client_id=client_record_id,
        business_id=business_id,
        note_id=note_id,
        actor_id=user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
