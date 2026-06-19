from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.path_params import PathId
from app.reminders.api.reminder_responses import REMINDER_DETAIL_RESPONSES
from app.reminders.schemas.reminder import ReminderResponse
from app.reminders.services.reminder_service import ReminderService
from app.users.api.user_deps import CurrentUser, DBSession

get_router = APIRouter()


@get_router.get(
    "/{reminder_id:int}",
    response_model=ReminderResponse,
    responses=REMINDER_DETAIL_RESPONSES,
)
def get_reminder(
    reminder_id: PathId,
    db: DBSession,
    _user: CurrentUser,
):
    service = ReminderService(db)
    reminder = service.get_reminder(reminder_id)
    if not reminder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="התזכורת לא נמצאה")
    return service.to_response(reminder)
