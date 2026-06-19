from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.pagination import MAX_PAGE_SIZE
from app.reminders.models.reminder import ReminderStatus
from app.reminders.schemas.reminder import ReminderListResponse
from app.reminders.services.reminder_service import ReminderService
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

list_router = APIRouter()


@list_router.get(
    "/",
    response_model=ReminderListResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def list_reminders(
    db: DBSession,
    _user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    status_filter: ReminderStatus | None = Query(None, alias="status"),
):
    service = ReminderService(db)
    items, total = service.get_reminders(
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return ReminderListResponse(
        items=service.to_responses(items),
        page=page,
        page_size=page_size,
        total=total,
    )
