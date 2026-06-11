from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.exceptions import not_found_response
from app.reminders.schemas.reminders import ReminderResponse
from app.reminders.services.reminder_service import ReminderService
from app.users.api.deps import CurrentUser, DBSession

get_router = APIRouter()


@get_router.get(
    "/{reminder_id:int}",
    response_model=ReminderResponse,
    responses=not_found_response(description="התזכורת המבוקשת לא נמצאה"),
)
def get_reminder(
    reminder_id: int,
    db: DBSession,
    _user: CurrentUser,
):
    service = ReminderService(db)
    reminder = service.get_reminder(reminder_id)
    if not reminder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="התזכורת לא נמצאה")
    return service.to_response(reminder)
