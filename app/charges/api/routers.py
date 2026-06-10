"""Charge API router aggregating sub-routers."""

from fastapi import APIRouter

from app.charges.api.charge import router as charge_router

router = APIRouter()
router.include_router(charge_router)

__all__ = ["router"]
