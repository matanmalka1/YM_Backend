"""Clients API router aggregating sub-routers."""

from fastapi import APIRouter

from app.clients.api.client_routes_tasks import router as client_tasks_router
from app.clients.api.client_routes import router as clients_router
from app.clients.api.client_routes_excel import router as clients_excel_router

router = APIRouter()
router.include_router(clients_excel_router)
router.include_router(clients_router)
router.include_router(client_tasks_router)

__all__ = ["router"]
