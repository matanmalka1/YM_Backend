from fastapi import APIRouter, Depends, Query, Response, status

from app.businesses.api.business_responses import (
    BUSINESS_ACTION_RESPONSES,
    BUSINESS_CREATE_RESPONSES,
    BUSINESS_UPDATE_RESPONSES,
)
from app.businesses.schemas.business_schemas import (
    BusinessCreateRequest,
    BusinessResponse,
    BusinessUpdateRequest,
    ClientBusinessesResponse,
)
from app.businesses.services.business_service import BusinessService
from app.businesses.services.business_client_business_service import ClientBusinessService
from app.core.openapi_responses import not_found_response
from app.core.pagination import MAX_PAGE_SIZE
from app.core.path_params import PathId
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

client_businesses_router = APIRouter(
    prefix="/clients/{client_record_id}/businesses",
    tags=["businesses"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@client_businesses_router.post(
    "",
    response_model=BusinessResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=BUSINESS_CREATE_RESPONSES,
)
def create_business(
    client_record_id: PathId, request: BusinessCreateRequest, db: DBSession, user: CurrentUser
):
    """יצירת עסק חדש תחת לקוח קיים (ADVISOR only)."""
    business = BusinessService(db).create_business(
        client_id=client_record_id,
        opened_at=request.opened_at,
        business_name=request.business_name,
        notes=request.notes,
        actor_id=user.id,
    )
    return ClientBusinessService(db).to_response(business, client_id=client_record_id)


@client_businesses_router.get(
    "",
    response_model=ClientBusinessesResponse,
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def list_client_businesses(
    client_record_id: PathId,
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    return ClientBusinessService(db).list_for_client(
        client_record_id,
        page=page,
        page_size=page_size,
    )


@client_businesses_router.get(
    "/{business_id}",
    response_model=BusinessResponse,
    responses=not_found_response(description="העסק המבוקש לא נמצא"),
)
def get_business(client_record_id: PathId, business_id: PathId, db: DBSession, user: CurrentUser):
    service = ClientBusinessService(db)
    business = service.get_for_client(client_record_id, business_id)
    return service.to_response(business, client_id=client_record_id)


@client_businesses_router.patch(
    "/{business_id}",
    response_model=BusinessResponse,
    responses=BUSINESS_UPDATE_RESPONSES,
)
def update_business(
    client_record_id: PathId,
    business_id: PathId,
    request: BusinessUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    business = BusinessService(db).update_business(
        business_id,
        client_id=client_record_id,
        user_role=user.role,
        actor_id=user.id,
        **request.model_dump(exclude_unset=True),
    )
    return ClientBusinessService(db).to_response(business, client_id=client_record_id)


@client_businesses_router.delete(
    "/{business_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=BUSINESS_ACTION_RESPONSES,
)
def delete_business(
    client_record_id: PathId, business_id: PathId, db: DBSession, user: CurrentUser
):
    ClientBusinessService(db).delete_for_client(client_record_id, business_id, actor_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@client_businesses_router.post(
    "/{business_id}/restore",
    response_model=BusinessResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=BUSINESS_ACTION_RESPONSES,
)
def restore_business(
    client_record_id: PathId, business_id: PathId, db: DBSession, user: CurrentUser
):
    service = ClientBusinessService(db)
    business = service.restore_for_client(
        client_record_id,
        business_id,
        actor_id=user.id,
        actor_role=user.role,
    )
    return service.to_response(business, client_id=client_record_id)
