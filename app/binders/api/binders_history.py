from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.binders.schemas.binder import (
    BinderHistoryResponse,
    BinderIntakeListResponse,
    BinderIntakePatchRequest,
    BinderIntakeResponse,
)
from app.binders.services.binder_history_service import BinderHistoryService
from app.binders.services.binder_intake_edit_service import BinderIntakeEditService
from app.binders.services.messages import BINDER_NOT_FOUND
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/binders",
    tags=["binders-history"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get("/{binder_id}/history", response_model=BinderHistoryResponse)
def get_binder_history(
    binder_id: int,
    db: DBSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    service = BinderHistoryService(db)
    result = service.get_binder_history(binder_id, page=page, page_size=page_size)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=BINDER_NOT_FOUND.format(binder_id=binder_id),
        )

    binder, logs, total = result
    return BinderHistoryResponse(
        binder_id=binder.id,
        history=service.build_history_entries(logs),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{binder_id}/intakes", response_model=BinderIntakeListResponse)
def get_binder_intakes(
    binder_id: int,
    db: DBSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    service = BinderHistoryService(db)
    intakes, total = service.get_binder_intakes(binder_id, page=page, page_size=page_size)
    return BinderIntakeListResponse(
        binder_id=binder_id,
        intakes=intakes,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/{binder_id}/intakes/{intake_id}", response_model=BinderIntakeResponse)
def patch_binder_intake(
    binder_id: int,
    intake_id: int,
    request: BinderIntakePatchRequest,
    db: DBSession,
    user: CurrentUser,
):
    intake = BinderIntakeEditService(db).edit_intake(
        intake_id=intake_id,
        actor_id=user.id,
        patch=request.model_dump(exclude_none=True),
        binder_id=binder_id,
    )
    return BinderIntakeResponse.model_validate(intake)
