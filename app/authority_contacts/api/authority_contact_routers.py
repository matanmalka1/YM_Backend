"""Authority contact API router aggregating sub-routers."""

from fastapi import APIRouter

from app.authority_contacts.api.authority_contact_routes import (
    router as authority_contact_router,
)

router = APIRouter()
router.include_router(authority_contact_router)

__all__ = ["router"]
