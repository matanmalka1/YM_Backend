from __future__ import annotations

from fastapi import APIRouter

from app.reminders.api.responses import REMINDER_CANCEL_RESPONSES
from app.reminders.schemas.reminders import ReminderResponse
from app.reminders.services.reminder_service import ReminderService
from app.users.api.deps import CurrentUser, DBSession

cancel_router = APIRouter()


@cancel_router.post(
    "/{reminder_id:int}/cancel",
    response_model=ReminderResponse,
    responses=REMINDER_CANCEL_RESPONSES,
)
def cancel_reminder(
    reminder_id: int,
    db: DBSession,
    _user: CurrentUser,
):
    service = ReminderService(db)
    reminder = service.cancel_reminder(reminder_id)
    return service.to_response(reminder)
