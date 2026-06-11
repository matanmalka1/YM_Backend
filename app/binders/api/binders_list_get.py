from fastapi import APIRouter, Depends, Query, Response, status

from app.binders.schemas.binder import BinderListResponse, BinderResponse
from app.binders.services.binder_list_service import BinderListService
from app.binders.services.binder_service import BinderService
from app.binders.services.messages import BINDER_NOT_FOUND
from app.core.exceptions import NotFoundError, not_found_response
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/binders",
    tags=["binders"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get("", response_model=BinderListResponse)
def list_binders(
    db: DBSession,
    user: CurrentUser,
    location_status: str | None = None,
    capacity_status: str | None = None,
    client_record_id: int | None = None,
    query: str | None = None,
    client_name: str | None = None,
    binder_number: str | None = None,
    year: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str | None = Query(None),
    order: str = Query("desc"),
):
    """List active binders with optional filters, sorting, and pagination."""
    service = BinderListService(db)
    items, total, counters = service.list_binders_enriched(
        client_record_id=client_record_id,
        location_status=location_status,
        capacity_status=capacity_status,
        query=query,
        client_name_filter=client_name,
        binder_number=binder_number,
        year=year,
        sort_by=sort_by or "period_start",
        order=order,
        page=page,
        page_size=page_size,
    )
    return BinderListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        counters=counters,
    )


@router.get(
    "/{binder_id}",
    response_model=BinderResponse,
    responses=not_found_response(description="הקלסר המבוקש לא נמצא"),
)
def get_binder(binder_id: int, db: DBSession, user: CurrentUser):
    """Get binder by ID."""
    service = BinderListService(db)
    binder_response = service.get_binder_with_client_name(binder_id)
    if not binder_response:
        raise NotFoundError(BINDER_NOT_FOUND.format(binder_id=binder_id), "BINDER.NOT_FOUND")
    return binder_response


@router.delete(
    "/{binder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=not_found_response(description="הקלסר המבוקש לא נמצא"),
)
def delete_binder(binder_id: int, db: DBSession, user: CurrentUser):
    """Soft-delete a binder (ADVISOR only)."""
    service = BinderService(db)
    deleted = service.delete_binder(binder_id, actor_id=user.id)
    if not deleted:
        raise NotFoundError(BINDER_NOT_FOUND.format(binder_id=binder_id), "BINDER.NOT_FOUND")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
