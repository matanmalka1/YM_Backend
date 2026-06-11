from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.binders.schemas.binder import (
    BinderAuditResponse,
    BinderIntakeListResponse,
    BinderIntakeResponse,
    BinderIntakeUpdateRequest,
)
from app.binders.services.binder_audit_service import BinderAuditService
from app.binders.services.binder_intake_edit_service import BinderIntakeEditService
from app.binders.services.messages import BINDER_NOT_FOUND
from app.core.exceptions import not_found_response
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/binders",
    tags=["binders-audit"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get(
    "/{binder_id}/audit",
    response_model=BinderAuditResponse,
    responses=not_found_response(description="הקלסר המבוקש לא נמצא"),
)
def get_binder_audit(
    binder_id: int,
    db: DBSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    service = BinderAuditService(db)
    result = service.get_binder_audit(binder_id, page=page, page_size=page_size)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=BINDER_NOT_FOUND.format(binder_id=binder_id),
        )

    binder, logs, total = result
    return BinderAuditResponse(
        binder_id=binder.id,
        audit=service.build_audit_entries(logs),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{binder_id}/intakes",
    response_model=BinderIntakeListResponse,
    responses=not_found_response(description="הקלסר המבוקש לא נמצא"),
)
def get_binder_intakes(
    binder_id: int,
    db: DBSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    service = BinderAuditService(db)
    intakes, total = service.get_binder_intakes(binder_id, page=page, page_size=page_size)
    return BinderIntakeListResponse(
        binder_id=binder_id,
        intakes=intakes,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/{binder_id}/intakes/{intake_id}",
    response_model=BinderIntakeResponse,
    responses=not_found_response(description="הקלסר המבוקש לא נמצא"),
)
def patch_binder_intake(
    binder_id: int,
    intake_id: int,
    request: BinderIntakeUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    intake = BinderIntakeEditService(db).edit_intake(
        intake_id=intake_id,
        actor_id=user.id,
        patch=request.model_dump(exclude_unset=True),
        binder_id=binder_id,
    )
    return BinderIntakeResponse.model_validate(intake)
