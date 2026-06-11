from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import not_found_response
from app.reminders.schemas.reminders import ReminderResponse
from app.reminders.services.reminder_service import ReminderService
from app.users.api.deps import CurrentUser, DBSession

cancel_router = APIRouter()


@cancel_router.post(
    "/{reminder_id:int}/cancel",
    response_model=ReminderResponse,
    responses=not_found_response(description="התזכורת המבוקשת לא נמצאה"),
)
def cancel_reminder(
    reminder_id: int,
    db: DBSession,
    _user: CurrentUser,
):
    service = ReminderService(db)
    reminder = service.cancel_reminder(reminder_id)
    return service.to_response(reminder)
