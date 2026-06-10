"""Invoice API router aggregating sub-routers."""

from fastapi import APIRouter

from app.invoices.api.invoices import router as invoices_router

router = APIRouter()
router.include_router(invoices_router)

__all__ = ["router"]
