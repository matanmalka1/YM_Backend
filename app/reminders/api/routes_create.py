from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.reminders.api.responses import REMINDER_CREATE_RESPONSES
from app.reminders.schemas.reminders import ReminderCreateRequest, ReminderResponse
from app.reminders.services.reminder_service import ReminderService
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

create_router = APIRouter()


@create_router.post(
    "/",
    response_model=ReminderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=REMINDER_CREATE_RESPONSES,
)
def create_reminder(
    request: ReminderCreateRequest,
    db: DBSession,
    user: CurrentUser,
):
    service = ReminderService(db)
    reminder = service.create_from_request(request, created_by_user_id=user.id)
    return service.to_response(reminder)
