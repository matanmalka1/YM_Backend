import logging
from time import perf_counter

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings
from app.core.logging_config import (
    clear_request_id,
    clear_request_log_stats,
    get_logger,
    get_request_log_stats,
    has_request_db_activity,
    log_request_summary,
    record_sql_query,
)

logger = get_logger(__name__)

if settings.APP_ENV == "production" and settings.DATABASE_URL.startswith("sqlite"):
    raise RuntimeError("SQLite אינו מותר בסביבת ייצור")

# Create engine
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)


@event.listens_for(engine, "before_cursor_execute")
def _record_query_start(conn, _cursor, statement, parameters, context, _executemany):
    context._query_start_time = perf_counter()


@event.listens_for(engine, "after_cursor_execute")
def _record_query_end(conn, _cursor, statement, parameters, context, _executemany):
    start_time = getattr(context, "_query_start_time", None)
    if start_time is None:
        return

    record_sql_query(statement, (perf_counter() - start_time) * 1000)


logging.getLogger("sqlalchemy.engine").setLevel(
    logging.INFO if settings.LOG_SQL else logging.WARNING
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Base class for ORM models
class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency for FastAPI routes to get DB session.

    Commits on clean exit; rolls back on any exception.
    Services that coordinate external I/O (e.g. storage uploads) may call
    db.commit() / db.rollback() themselves — the safety net here is a no-op
    on top of an already-committed session.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        stats = get_request_log_stats()
        if (
            stats is not None
            and has_request_db_activity()
            and stats.status_code is not None
        ):
            log_request_summary(
                logger,
                service="binder-billing-crm",
                env=settings.APP_ENV,
                slow_request_ms=settings.LOG_SLOW_REQUEST_MS,
                slow_query_ms=settings.LOG_SLOW_QUERY_MS,
                high_query_count=settings.LOG_HIGH_QUERY_COUNT,
            )
            clear_request_log_stats()
            clear_request_id()
