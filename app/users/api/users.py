from fastapi import APIRouter, Depends, Query, status

from app.core.exceptions import not_found_response
from app.users.api.deps import CurrentUser, DBSession, require_role
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


@router.post("", response_model=UserManagementResponse, status_code=status.HTTP_201_CREATED)
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
    )


@router.get("", response_model=UserManagementListResponse)
def list_users(
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
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
def get_user(user_id: int, db: DBSession, user: CurrentUser):
    service = UserManagementService(db)
    return service.get_user(actor_role=user.role, user_id=user_id)


@router.patch(
    "/{user_id}",
    response_model=UserManagementResponse,
    responses=not_found_response(description="המשתמש המבוקש לא נמצא"),
)
def update_user(user_id: int, request: UserUpdateRequest, db: DBSession, user: CurrentUser):
    service = UserManagementService(db)
    update_data = request.model_dump(exclude_unset=True)
    return service.update_user(
        actor_user_id=user.id,
        actor_role=user.role,
        user_id=user_id,
        **update_data,
    )


@router.post(
    "/{user_id}/activate",
    response_model=UserManagementResponse,
    responses=not_found_response(description="המשתמש המבוקש לא נמצא"),
)
def activate_user(user_id: int, db: DBSession, user: CurrentUser):
    service = UserManagementService(db)
    return service.activate_user(
        actor_user_id=user.id,
        actor_role=user.role,
        user_id=user_id,
    )


@router.post(
    "/{user_id}/deactivate",
    response_model=UserManagementResponse,
    responses=not_found_response(description="המשתמש המבוקש לא נמצא"),
)
def deactivate_user(user_id: int, db: DBSession, user: CurrentUser):
    service = UserManagementService(db)
    return service.deactivate_user(
        actor_user_id=user.id,
        actor_role=user.role,
        target_user_id=user_id,
    )


@router.post(
    "/{user_id}/reset-password",
    response_model=UserManagementResponse,
    responses=not_found_response(description="המשתמש המבוקש לא נמצא"),
)
def reset_password(user_id: int, request: PasswordResetRequest, db: DBSession, user: CurrentUser):
    service = UserManagementService(db)
    return service.reset_password(
        actor_user_id=user.id,
        actor_role=user.role,
        target_user_id=user_id,
        new_password=request.new_password,
    )
