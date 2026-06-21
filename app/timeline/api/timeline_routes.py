from fastapi import APIRouter, Depends, Query

from app.core.openapi_responses import not_found_response
from app.core.path_params import PathId
from app.timeline.schemas.timeline import ClientTimelineResponse, TimelineEvent
from app.timeline.services.timeline_service import DEFAULT_TIMELINE_PAGE_SIZE, TimelineService
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
    search: str | None = Query(None),
    event_type: list[str] | None = Query(None),
    important_only: bool = Query(False),
):
    """Get unified client timeline."""
    service = TimelineService(db)
    events, total = service.get_client_timeline(
        client_record_id=client_record_id,
        page=page,
        search=search,
        event_types=event_type,
        important_only=important_only,
    )

    return ClientTimelineResponse(
        client_record_id=client_record_id,
        events=[TimelineEvent(**e) for e in events],
        page=page,
        page_size=DEFAULT_TIMELINE_PAGE_SIZE,
        total=total,
    )
