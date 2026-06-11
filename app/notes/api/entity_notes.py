from fastapi import APIRouter, Depends, Query, Response, status

from app.core.exceptions import not_found_response
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
    prefix="/clients/{client_id}/notes",
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
    client_id: int,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    service = EntityNoteService(db)
    items, total = service.list_notes(
        entity_type=_ENTITY_TYPE,
        entity_id=client_id,
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
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def add_note(
    client_id: int,
    request: EntityNoteCreateRequest,
    db: DBSession,
    user: CurrentUser,
):
    service = EntityNoteService(db)
    note = service.add_note(
        entity_type=_ENTITY_TYPE,
        entity_id=client_id,
        note=request.note,
        created_by=user.id,
    )
    return EntityNoteResponse.model_validate(note)


@router.patch(
    "/{note_id}",
    response_model=EntityNoteResponse,
    responses=not_found_response(description="ההערה המבוקשת לא נמצאה"),
)
def update_note(
    client_id: int,
    note_id: int,
    request: EntityNoteUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    service = EntityNoteService(db)
    note = service.update_note(
        note_id=note_id,
        entity_type=_ENTITY_TYPE,
        entity_id=client_id,
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
    client_id: int,
    note_id: int,
    db: DBSession,
    user: CurrentUser,
):
    service = EntityNoteService(db)
    service.delete_note(
        note_id=note_id,
        entity_type=_ENTITY_TYPE,
        entity_id=client_id,
        actor_id=user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
