from fastapi import APIRouter

from app.notifications.api.notifications import router as notifications_router

router = APIRouter()
router.include_router(notifications_router)

__all__ = ["router"]
