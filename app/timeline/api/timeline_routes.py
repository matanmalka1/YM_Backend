from fastapi import APIRouter, Depends, Query

from app.core.openapi_responses import not_found_response
from app.core.pagination import MAX_PAGE_SIZE
from app.core.path_params import PathId
from app.timeline.schemas.timeline import ClientTimelineResponse, TimelineEvent
from app.timeline.services.timeline_service import TimelineService
from app.users.api.user_deps import DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/clients",
    tags=["timeline"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get(
    "/{client_record_id}/timeline",
    response_model=ClientTimelineResponse,
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def get_client_timeline(
    client_record_id: PathId,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = Query(None),
    event_type: list[str] | None = Query(None),
    important_only: bool = Query(False),
):
    """Get unified client timeline."""
    service = TimelineService(db)
    events, total = service.get_client_timeline(
        client_record_id=client_record_id,
        page=page,
        page_size=page_size,
        search=search,
        event_types=event_type,
        important_only=important_only,
    )

    return ClientTimelineResponse(
        client_record_id=client_record_id,
        events=[TimelineEvent(**e) for e in events],
        page=page,
        page_size=page_size,
        total=total,
    )
