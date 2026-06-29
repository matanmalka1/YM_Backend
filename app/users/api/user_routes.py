from fastapi import APIRouter, Depends, Query, status

from app.core.openapi_responses import not_found_response
from app.core.pagination import MAX_PAGE_SIZE
from app.core.path_params import PathId
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.api.user_responses import (
    USER_ACTIVATE_RESPONSES,
    USER_CREATE_RESPONSES,
    USER_DEACTIVATE_RESPONSES,
    USER_RESET_PASSWORD_RESPONSES,
    USER_UPDATE_RESPONSES,
)
from app.users.models.user import UserRole
from app.users.schemas.user_management import (
    PasswordResetRequest,
    UserCreateRequest,
    UserManagementListResponse,
    UserManagementResponse,
    UserUpdateRequest,
)
from app.users.services.user_management_service import UserManagementService

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)


@router.post(
    "",
    response_model=UserManagementResponse,
    status_code=status.HTTP_201_CREATED,
    responses=USER_CREATE_RESPONSES,
)
def create_user(request: UserCreateRequest, db: DBSession, user: CurrentUser):
    service = UserManagementService(db)
    return service.create_user(
        actor_user_id=user.id,
        actor_role=user.role,
        full_name=request.full_name,
        email=request.email,
        role=request.role,
        password=request.password,
        phone=request.phone,
        actor_name=user.full_name,
    )


@router.get("", response_model=UserManagementListResponse)
def list_users(
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    is_active: bool | None = Query(None),
    search: str | None = Query(None),
):
    service = UserManagementService(db)
    items, total = service.list_users(
        actor_role=user.role,
        page=page,
        page_size=page_size,
        is_active=is_active,
        search=search,
    )
    return UserManagementListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/{user_id}",
    response_model=UserManagementResponse,
    responses=not_found_response(description="המשתמש המבוקש לא נמצא"),
)
def get_user(user_id: PathId, db: DBSession, user: CurrentUser):
    service = UserManagementService(db)
    return service.get_user(actor_role=user.role, user_id=user_id)


@router.patch(
    "/{user_id}",
    response_model=UserManagementResponse,
    responses=USER_UPDATE_RESPONSES,
)
def update_user(user_id: PathId, request: UserUpdateRequest, db: DBSession, user: CurrentUser):
    service = UserManagementService(db)
    update_data = request.model_dump(exclude_unset=True)
    return service.update_user(
        actor_user_id=user.id,
        actor_role=user.role,
        user_id=user_id,
        actor_name=user.full_name,
        **update_data,
    )


@router.post(
    "/{user_id}/activate",
    response_model=UserManagementResponse,
    responses=USER_ACTIVATE_RESPONSES,
)
def activate_user(user_id: PathId, db: DBSession, user: CurrentUser):
    service = UserManagementService(db)
    return service.activate_user(
        actor_user_id=user.id,
        actor_role=user.role,
        user_id=user_id,
        actor_name=user.full_name,
    )


@router.post(
    "/{user_id}/deactivate",
    response_model=UserManagementResponse,
    responses=USER_DEACTIVATE_RESPONSES,
)
def deactivate_user(user_id: PathId, db: DBSession, user: CurrentUser):
    service = UserManagementService(db)
    return service.deactivate_user(
        actor_user_id=user.id,
        actor_role=user.role,
        target_user_id=user_id,
        actor_name=user.full_name,
    )


@router.post(
    "/{user_id}/reset-password",
    response_model=UserManagementResponse,
    responses=USER_RESET_PASSWORD_RESPONSES,
)
def reset_password(
    user_id: PathId, request: PasswordResetRequest, db: DBSession, user: CurrentUser
):
    service = UserManagementService(db)
    return service.reset_password(
        actor_user_id=user.id,
        actor_role=user.role,
        target_user_id=user_id,
        new_password=request.new_password,
        actor_name=user.full_name,
    )
