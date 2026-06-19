"""VAT Reports API router — aggregates all sub-routers."""

from fastapi import APIRouter

from app.vat.api.vat_routes_client_summary import router as client_summary_router
from app.vat.api.vat_routes_data_entry import router as data_entry_router
from app.vat.api.vat_routes_filing import router as filing_router
from app.vat.api.vat_routes_grouped import router as grouped_router
from app.vat.api.vat_routes_intake import router as intake_router
from app.vat.api.vat_routes_queries import router as queries_router
from app.vat.api.vat_routes_status import router as status_router
from app.vat.api.vat_routes_work_items import router as work_items_router

router = APIRouter()
router.include_router(intake_router)
router.include_router(work_items_router)
router.include_router(data_entry_router)
router.include_router(status_router)
router.include_router(filing_router)
router.include_router(grouped_router)
router.include_router(queries_router)
router.include_router(client_summary_router)

__all__ = ["router"]
