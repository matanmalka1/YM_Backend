"""Routes: grouped VAT work items by due date."""

from fastapi import APIRouter, Depends, Query

from app.common.enums import VatType
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.schemas.vat_report import (
    VatWorkItemGroupItemsResponse,
    VatWorkItemGroupsResponse,
    VatWorkItemGroupSummary,
)
from app.vat import vat_grouped_enrichment

router = APIRouter(prefix="/vat", tags=["vat-reports"])


@router.get(
    "/work-items/groups",
    response_model=VatWorkItemGroupsResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def list_work_item_groups(
    db: DBSession,
    current_user: CurrentUser,
    period_type: VatType | None = Query(None),
    status_filter: VatWorkItemStatus | None = Query(default=None, alias="status"),
    client_record_id: int | None = Query(None),
    client_name: str | None = Query(None),
    year: int | None = Query(None),
):
    groups = vat_grouped_enrichment.get_groups(
        db,
        period_type=period_type,
        client_record_id=client_record_id,
        client_name=client_name,
        status=status_filter,
        year=year,
    )
    return VatWorkItemGroupsResponse(groups=[VatWorkItemGroupSummary(**g) for g in groups])


@router.get(
    "/work-items/groups/{group_key}/items",
    response_model=VatWorkItemGroupItemsResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def list_work_item_group_items(
    group_key: str,
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    status_filter: VatWorkItemStatus | None = Query(default=None, alias="status"),
    client_record_id: int | None = Query(None),
    client_name: str | None = Query(None),
):
    result = vat_grouped_enrichment.get_group_items_enriched(
        db,
        group_key=group_key,
        page=page,
        page_size=page_size,
        client_record_id=client_record_id,
        client_name=client_name,
        status=status_filter,
        user_role=current_user.role,
    )
    return VatWorkItemGroupItemsResponse(**result)
