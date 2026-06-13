from fastapi import APIRouter, Depends, Query, Response, status

from app.core.openapi_responses import not_found_response
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.notes.api.responses import ENTITY_NOTE_CREATE_RESPONSES, NOTE_UPDATE_RESPONSES
from app.notes.schemas.entity_note import (
    EntityNoteCreateRequest,
    EntityNoteListResponse,
    EntityNoteResponse,
    EntityNoteUpdateRequest,
)
from app.notes.services.entity_note_service import EntityNoteService
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/clients/{client_record_id}/notes",
    tags=["notes"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)

_ENTITY_TYPE = "client"


@router.get(
    "",
    response_model=EntityNoteListResponse,
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def list_notes(
    client_record_id: int,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    service = EntityNoteService(db)
    items, total = service.list_notes(
        entity_type=_ENTITY_TYPE,
        entity_id=client_record_id,
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
    responses=ENTITY_NOTE_CREATE_RESPONSES,
)
def add_note(
    client_record_id: int,
    request: EntityNoteCreateRequest,
    db: DBSession,
    user: CurrentUser,
):
    service = EntityNoteService(db)
    note = service.add_note(
        entity_type=_ENTITY_TYPE,
        entity_id=client_record_id,
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
    note_id: int,
    request: EntityNoteUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    service = EntityNoteService(db)
    note = service.update_note(
        note_id=note_id,
        entity_type=_ENTITY_TYPE,
        entity_id=client_record_id,
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
    note_id: int,
    db: DBSession,
    user: CurrentUser,
):
    service = EntityNoteService(db)
    service.delete_note(
        note_id=note_id,
        entity_type=_ENTITY_TYPE,
        entity_id=client_record_id,
        actor_id=user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
