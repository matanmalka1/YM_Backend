"""Routes: read-only audit trail queries."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.audit.schemas.audit_entity_audit_log import EntityAuditTrailResponse
from app.audit.services.audit_trail_service import AuditTrailService
from app.core.openapi_responses import bad_request_response, error_responses, not_found_response
from app.core.pagination import MAX_PAGE_SIZE
from app.core.path_params import PathId
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get(
    "/{entity_type}/{entity_id}",
    response_model=EntityAuditTrailResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=error_responses(
        bad_request_response(description="סוג הישות המבוקש אינו נתמך"),
        not_found_response(description="הישות המבוקשת לא נמצאה"),
    ),
)
def get_entity_audit_trail(
    entity_type: str,
    entity_id: PathId,
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    action: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
):
    """Get the full audit trail for any audited entity."""
    return AuditTrailService(db).get_entity_audit_trail(
        entity_type,
        entity_id,
        page,
        page_size,
        current_user=current_user,
        action=action,
        user_id=user_id,
        created_after=created_after,
        created_before=created_before,
    )
