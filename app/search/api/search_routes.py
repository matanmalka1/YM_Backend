from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import StringConstraints

from app.core.api_types import PaginatedResponse
from app.core.pagination import MAX_PAGE_SIZE
from app.search.schemas.search import SearchMatch, SearchMatchType, SearchResponse
from app.search.services.search_service import SearchService
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/search",
    tags=["search"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)

# Stripped before validation so a whitespace-only term is a 422, not an empty search.
# max_length is defensive hardening; no real identifier or title approaches it.
SearchTerm = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


@router.get("", response_model=SearchResponse)
def search(
    db: DBSession,
    user: CurrentUser,
    search: SearchTerm,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    """Resolve the term to clients and to matching records; pagination pages the clients."""
    return SearchService(db).search(search, page=page, page_size=page_size)


@router.get("/items", response_model=PaginatedResponse[SearchMatch])
def list_items(
    db: DBSession,
    user: CurrentUser,
    search: SearchTerm,
    result_type: SearchMatchType,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    """One type's matches for the term, in full — an expanded preview group."""
    return SearchService(db).list_matches(search, result_type, page, page_size)
