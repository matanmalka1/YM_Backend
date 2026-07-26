import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.background_jobs import (
    daily_annual_report_signature_reconciliation_job,
    daily_expiry_job,
    run_development_tax_calendar_bootstrap_service,
    run_startup_annual_report_signature_reconciliation,
    run_startup_expiry,
)
from app.core.logging_config import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting")
    run_development_tax_calendar_bootstrap_service()
    run_startup_expiry()
    run_startup_annual_report_signature_reconciliation()
    expiry_task = asyncio.create_task(daily_expiry_job())
    signature_reconciliation_task = asyncio.create_task(
        daily_annual_report_signature_reconciliation_job()
    )
    yield
    expiry_task.cancel()
    signature_reconciliation_task.cancel()
    logger.info("Application shutting down")
