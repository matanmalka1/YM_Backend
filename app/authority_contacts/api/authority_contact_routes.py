from fastapi import APIRouter, Depends, Query, status

from app.authority_contacts.api.authority_contact_responses import (
    AUTHORITY_CONTACT_CREATE_RESPONSES,
    AUTHORITY_CONTACT_UPDATE_RESPONSES,
)
from app.authority_contacts.models.authority_contact import ContactType
from app.authority_contacts.schemas.authority_contact import (
    AuthorityContactCreateRequest,
    AuthorityContactListResponse,
    AuthorityContactResponse,
    AuthorityContactUpdateRequest,
)
from app.authority_contacts.services.authority_contact_service import (
    AuthorityContactService,
)
from app.core.openapi_responses import not_found_response
from app.core.pagination import MAX_PAGE_SIZE
from app.core.path_params import PathId
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/clients",
    tags=["authority-contacts"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


def _to_contact_response(contact) -> AuthorityContactResponse:
    response = AuthorityContactResponse.model_validate(contact)
    return response


@router.post(
    "/{client_record_id}/authority-contacts",
    response_model=AuthorityContactResponse,
    status_code=status.HTTP_201_CREATED,
    responses=AUTHORITY_CONTACT_CREATE_RESPONSES,
)
def create_authority_contact(
    client_record_id: PathId,
    request: AuthorityContactCreateRequest,
    db: DBSession,
    _: CurrentUser,
):
    """Create new authority contact for client."""
    service = AuthorityContactService(db)
    contact = service.add_contact(
        client_record_id=client_record_id,
        contact_type=request.contact_type,
        name=request.name,
        office=request.office,
        phone=request.phone,
        email=request.email,
        notes=request.notes,
    )
    return _to_contact_response(contact)


@router.get(
    "/{client_record_id}/authority-contacts",
    response_model=AuthorityContactListResponse,
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def list_authority_contacts(
    client_record_id: PathId,
    db: DBSession,
    _: CurrentUser,
    contact_type: ContactType | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    """List authority contacts for client with pagination."""
    service = AuthorityContactService(db)
    contacts, total = service.list_client_contacts(
        client_record_id,
        contact_type,
        page=page,
        page_size=page_size,
    )
    return AuthorityContactListResponse(
        items=[_to_contact_response(c) for c in contacts],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/{client_record_id}/authority-contacts/{contact_id}",
    response_model=AuthorityContactResponse,
    responses=not_found_response(description="איש הקשר המבוקש לא נמצא"),
)
def get_authority_contact(
    client_record_id: PathId,
    contact_id: PathId,
    db: DBSession,
    _: CurrentUser,
):
    """Get a single authority contact by ID, scoped to client."""
    service = AuthorityContactService(db)
    return _to_contact_response(service.get_contact(client_record_id, contact_id))


@router.patch(
    "/{client_record_id}/authority-contacts/{contact_id}",
    response_model=AuthorityContactResponse,
    responses=AUTHORITY_CONTACT_UPDATE_RESPONSES,
)
def update_authority_contact(
    client_record_id: PathId,
    contact_id: PathId,
    request: AuthorityContactUpdateRequest,
    db: DBSession,
    _: CurrentUser,
):
    """Update authority contact, scoped to client."""
    service = AuthorityContactService(db)
    update_data = request.model_dump(exclude_unset=True)
    contact = service.update_contact(client_record_id, contact_id, **update_data)
    return _to_contact_response(contact)


@router.delete(
    "/{client_record_id}/authority-contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=not_found_response(description="איש הקשר המבוקש לא נמצא"),
)
def delete_authority_contact(
    client_record_id: PathId, contact_id: PathId, db: DBSession, user: CurrentUser
):
    """Delete authority contact (ADVISOR only), scoped to client."""
    service = AuthorityContactService(db)
    service.delete_contact(client_record_id, contact_id, actor_id=user.id)
