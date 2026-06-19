from fastapi import APIRouter

from app.tax_calendar.api.tax_calendar_routes_groups import router as groups_router
from app.tax_calendar.api.tax_calendar_routes_settings import router as settings_router

router = APIRouter()
router.include_router(groups_router)
router.include_router(settings_router)

__all__ = ["router"]
