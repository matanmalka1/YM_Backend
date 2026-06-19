"""Health API router aggregating sub-routers."""

from fastapi import APIRouter

from app.health.api.health_routes import router as health_router

router = APIRouter()
router.include_router(health_router)

__all__ = ["router"]
