from fastapi import APIRouter, Depends, Query

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
    tags=["binders-operations"],
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
):
    """List binders that have not been handed over."""
    service = BinderOperationsService(db)
    items, total = service.get_open_binders(page=page, page_size=page_size)
    return _build_response(items, service, page, page_size, total)
