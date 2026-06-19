from fastapi import APIRouter

from app.notifications.api.notification_routes import router as notifications_router

router = APIRouter()
router.include_router(notifications_router)

__all__ = ["router"]
