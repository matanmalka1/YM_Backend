"""Binders API router aggregating sub-routers."""

from fastapi import APIRouter

from app.binders.api.binders_audit import router as binders_audit_router
from app.binders.api.binders_list_get import router as binders_list_get_router
from app.binders.api.binders_operations import router as binders_operations_router
from app.binders.api.binders_receive_return import (
    router as binders_receive_return_router,
)
from app.binders.api.client_binders_router import router as client_binders_router

router = APIRouter()
router.include_router(binders_operations_router)
router.include_router(binders_receive_return_router)
router.include_router(binders_list_get_router)
router.include_router(binders_audit_router)
router.include_router(client_binders_router)

__all__ = ["router"]
