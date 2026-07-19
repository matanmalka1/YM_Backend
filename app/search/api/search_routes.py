from fastapi import APIRouter, Depends, Query

from app.binders.models.binder import BinderCapacityStatus, BinderLocationStatus
from app.clients.client_enums import ClientStatus
from app.common.enums import EntityType
from app.core.api_types import PaginatedResponse
from app.core.pagination import MAX_PAGE_SIZE
from app.search.schemas.search import SearchItem, SearchItemType, SearchResponse
from app.search.services.search_service import SearchService
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/search",
    tags=["search"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get("", response_model=SearchResponse)
def search(
    db: DBSession,
    user: CurrentUser,
    search: str | None = None,
    client_record_id: int | None = None,
    id_number: str | None = None,
    binder_number: str | None = None,
    client_status: ClientStatus | None = None,
    entity_type: EntityType | None = None,
    binder_location_status: BinderLocationStatus | None = None,
    binder_capacity_status: BinderCapacityStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    """Resolve the term to clients, and preview the selected client's items by type."""
    return SearchService(db).search(
        search=search,
        client_record_id=client_record_id,
        id_number=id_number,
        binder_number=binder_number,
        client_status=client_status,
        entity_type=entity_type,
        binder_location_status=binder_location_status,
        binder_capacity_status=binder_capacity_status,
        page=page,
        page_size=page_size,
    )


@router.get("/items", response_model=PaginatedResponse[SearchItem])
def list_items(
    db: DBSession,
    user: CurrentUser,
    client_record_id: int,
    result_type: SearchItemType,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    """One client's items of a single type, paginated — an expanded preview group."""
    return SearchService(db).list_items(client_record_id, result_type, page, page_size)
