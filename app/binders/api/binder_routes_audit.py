from fastapi import APIRouter, Depends, Query

from app.binders.api.binder_responses import BINDER_INTAKE_UPDATE_RESPONSES
from app.binders.schemas.binder import (
    BinderIntakeListResponse,
    BinderIntakeResponse,
    BinderIntakeUpdateRequest,
)
from app.binders.services.binder_intake_edit_service import BinderIntakeEditService
from app.binders.services.binder_intake_service import BinderIntakeService
from app.core.openapi_responses import not_found_response
from app.core.pagination import MAX_PAGE_SIZE
from app.core.path_params import PathId
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/binders",
    tags=["binders"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get(
    "/{binder_id}/intakes",
    response_model=BinderIntakeListResponse,
    responses=not_found_response(description="הקלסר המבוקש לא נמצא"),
)
def get_binder_intakes(
    binder_id: PathId,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    intakes, total = BinderIntakeService(db).get_binder_intakes(
        binder_id, page=page, page_size=page_size
    )
    return BinderIntakeListResponse(
        items=intakes,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/{binder_id}/intakes/{intake_id}",
    response_model=BinderIntakeResponse,
    responses=BINDER_INTAKE_UPDATE_RESPONSES,
)
def patch_binder_intake(
    binder_id: PathId,
    intake_id: PathId,
    request: BinderIntakeUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    intake = BinderIntakeEditService(db).edit_intake(
        intake_id=intake_id,
        actor_id=user.id,
        patch=request.model_dump(exclude_unset=True),
        binder_id=binder_id,
        actor_display_name=user.full_name,
    )
    return BinderIntakeResponse.model_validate(intake)
