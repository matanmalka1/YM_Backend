from datetime import date

from fastapi import APIRouter, Depends, Query

from app.binders.models.binder import BinderCapacityStatus, BinderLocationStatus
from app.binders.schemas.binder_extended import (
    BinderDetailResponse,
    BinderListResponseExtended,
)
from app.binders.services.binder_operations_service import BinderOperationsService
from app.core.pagination import MAX_PAGE_SIZE
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/binders",
    tags=["binders"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


def _build_response(
    items,
    service: BinderOperationsService,
    page: int,
    page_size: int,
    total: int,
) -> BinderListResponseExtended:
    enriched = [BinderDetailResponse(**service.enrich_binder(b)) for b in items]
    return BinderListResponseExtended(
        items=enriched,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/open", response_model=BinderListResponseExtended)
def list_open_binders(
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    client_record_id: int | None = Query(None),
    binder_number: str | None = Query(None),
    location_status: BinderLocationStatus | None = Query(None),
    capacity_status: BinderCapacityStatus | None = Query(None),
    created_after: date | None = Query(None),
    created_before: date | None = Query(None),
):
    """List binders that have not been handed over."""
    service = BinderOperationsService(db)
    items, total = service.get_open_binders(
        page=page,
        page_size=page_size,
        client_record_id=client_record_id,
        binder_number=binder_number,
        location_status=location_status,
        capacity_status=capacity_status,
        created_after=created_after,
        created_before=created_before,
    )
    return _build_response(items, service, page, page_size, total)
