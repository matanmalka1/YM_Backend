"""Businesses API router aggregating sub-routers."""

from fastapi import APIRouter

from app.businesses.api.business_routes_client_businesses import client_businesses_router
from app.businesses.api.business_routes_client_status_card import (
    router as client_status_card_router,
)

router = APIRouter()
router.include_router(client_businesses_router)
router.include_router(client_status_card_router)

__all__ = ["router"]
