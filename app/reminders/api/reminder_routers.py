from __future__ import annotations

from fastapi import APIRouter, Depends

from app.reminders.api.reminder_routes_cancel import cancel_router
from app.reminders.api.reminder_routes_create import create_router
from app.reminders.api.reminder_routes_get import get_router
from app.reminders.api.reminder_routes_list import list_router
from app.users.api.user_deps import require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/reminders",
    tags=["reminders"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
router.include_router(list_router)
router.include_router(get_router)
router.include_router(create_router)
router.include_router(cancel_router)
