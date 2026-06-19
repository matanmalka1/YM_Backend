from fastapi import APIRouter, Depends, Query

from app.common.enums import ObligationType
from app.core.openapi_responses import not_found_response
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.path_params import PathId
from app.tax_calendar.schemas.tax_calendar_grouped import (
    TaxCalendarGroupItemsResponse,
    TaxCalendarGroupListResponse,
)
from app.tax_calendar.services.tax_calendar_grouped_items_service import get_group_items
from app.tax_calendar.services.tax_calendar_grouped_service import list_groups_paginated
from app.users.api.user_deps import DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(prefix="/tax-calendar", tags=["tax-calendar"])


@router.get(
    "/groups",
    response_model=TaxCalendarGroupListResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def list_tax_calendar_groups(
    db: DBSession,
    tax_year_after: int | None = Query(None),
    tax_year_before: int | None = Query(None),
    obligation_type: ObligationType | None = Query(None),
    include_empty: bool = Query(False),
    client_record_id: int | None = Query(None),
    client_search: str | None = Query(None),
    status: str = Query("all", pattern="^(all|open|overdue|done)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    return list_groups_paginated(
        db,
        tax_year_after=tax_year_after,
        tax_year_before=tax_year_before,
        obligation_type=obligation_type,
        include_empty=include_empty,
        client_record_id=client_record_id,
        client_search=client_search,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/groups/{tax_calendar_entry_id}/items",
    response_model=TaxCalendarGroupItemsResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description="הישות המבוקשת לא נמצאה"),
)
def get_tax_calendar_group_items(
    tax_calendar_entry_id: PathId,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    client_search: str | None = Query(None),
    client_record_id: int | None = Query(None),
):
    return get_group_items(
        db,
        tax_calendar_entry_id,
        page=page,
        page_size=page_size,
        client_search=client_search,
        client_record_id=client_record_id,
    )
