"""Annual reports API router aggregating sub-routers."""

from fastapi import APIRouter

from app.annual_reports.api.annual_report_routes_annex import router as annex_router
from app.annual_reports.api.annual_report_routes_charges import router as charges_router
from app.annual_reports.api.annual_report_routes_client import clients_router
from app.annual_reports.api.annual_report_routes_create_read import (
    router as create_read_router,
)
from app.annual_reports.api.annual_report_routes_detail import router as detail_router
from app.annual_reports.api.annual_report_routes_export import router as export_router
from app.annual_reports.api.annual_report_routes_financials import router as financials_router
from app.annual_reports.api.annual_report_routes_schedule import router as schedule_router
from app.annual_reports.api.annual_report_routes_season import season_router
from app.annual_reports.api.annual_report_routes_status import router as status_router
from app.annual_reports.api.annual_report_routes_tax import router as tax_router

router = APIRouter()
router.include_router(annex_router)
router.include_router(detail_router)
router.include_router(financials_router)
router.include_router(create_read_router)
router.include_router(schedule_router)
router.include_router(status_router)
router.include_router(clients_router)
router.include_router(season_router)
router.include_router(export_router)
router.include_router(tax_router)
router.include_router(charges_router)

__all__ = ["router"]
