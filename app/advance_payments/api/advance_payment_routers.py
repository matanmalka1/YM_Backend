"""Advance payments API router aggregating sub-routers."""

from fastapi import APIRouter

from app.advance_payments.api.advance_payment_routes_generate import router as generate_router
from app.advance_payments.api.advance_payment_routes import router as payments_router
from app.advance_payments.api.advance_payment_routes_overview import overview_router

router = APIRouter()
router.include_router(payments_router)
router.include_router(overview_router)
router.include_router(generate_router)

__all__ = ["router"]
