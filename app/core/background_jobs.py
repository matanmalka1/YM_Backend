import asyncio
import os
from collections.abc import Callable

from app.config import settings
from app.core.logging_config import get_logger
from app.database import SessionLocal
from app.signature_requests.repositories.signature_request_repository import (
    SignatureRequestRepository,
)
from app.signature_requests.services.signature_request_admin_actions import expire_overdue_requests
from app.tax_calendar.services.tax_calendar_bootstrap import bootstrap_tax_calendar

logger = get_logger(__name__)

_INTERVAL: int = getattr(settings, "BACKGROUND_JOB_INTERVAL_SECONDS", 86_400)


def run_startup_expiry() -> None:
    db = SessionLocal()
    try:
        count = expire_overdue_requests(SignatureRequestRepository(db))
        db.commit()
        if count:
            logger.info("Expired %d overdue signature request(s) on startup", count)
    except Exception:
        db.rollback()
        logger.exception("Startup signature expiry failed")
        raise
    finally:
        db.close()


def run_development_tax_calendar_bootstrap() -> None:
    if settings.APP_ENV != "development":
        return
    if "PYTEST_CURRENT_TEST" in os.environ:
        return

    db = SessionLocal()
    try:
        result = bootstrap_tax_calendar(db)
        db.commit()
        logger.info(
            "Tax calendar bootstrap complete: rules created=%s skipped=%s, entries created=%s skipped=%s",
            result["rules_created"],
            result["rules_skipped"],
            result["entries_created"],
            result["entries_skipped"],
        )
        if result["warnings"]:
            logger.warning("Tax calendar bootstrap warnings: %s", result["warnings"])
    except Exception:
        db.rollback()
        logger.exception("Tax calendar bootstrap failed")
        raise
    finally:
        db.close()


async def _run_job(name: str, task: Callable) -> None:
    while True:
        await asyncio.sleep(_INTERVAL)
        db = SessionLocal()
        try:
            task(db)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("%s failed", name)
        finally:
            db.close()


def _expiry_task(db) -> None:
    count = expire_overdue_requests(SignatureRequestRepository(db))
    if count:
        logger.info("Daily job: expired %d overdue signature request(s)", count)


async def daily_expiry_job() -> None:
    await _run_job("daily_expiry_job", _expiry_task)
