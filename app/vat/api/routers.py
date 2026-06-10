"""VAT Reports API router — aggregates all sub-routers."""

from fastapi import APIRouter

from app.vat.api.routes_client_summary import router as client_summary_router
from app.vat.api.routes_data_entry import router as data_entry_router
from app.vat.api.routes_filing import router as filing_router
from app.vat.api.routes_grouped import router as grouped_router
from app.vat.api.routes_intake import router as intake_router
from app.vat.api.routes_queries import router as queries_router
from app.vat.api.routes_status import router as status_router

router = APIRouter()
router.include_router(intake_router)
router.include_router(data_entry_router)
router.include_router(status_router)
router.include_router(filing_router)
router.include_router(grouped_router)
router.include_router(queries_router)
router.include_router(client_summary_router)

__all__ = ["router"]
