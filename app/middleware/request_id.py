"""
Request ID middleware for request tracking.

Generates unique request ID for each request and propagates
it through logging context.
"""

import uuid
from collections.abc import Awaitable, Callable
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.core.logging_config import (
    begin_request_log_stats,
    clear_request_log_stats,
    get_logger,
    has_request_db_activity,
    log_request_summary,
    reset_request_id,
    set_request_error,
    set_request_id,
    set_request_summary_context,
)

logger = get_logger(__name__)

CallNext = Callable[[Request], Awaitable[Response]]

_SKIP_LOG_PATHS = frozenset(
    {
        "/",
        "/health",
        "/ready",
        "/docs",
        "/openapi.json",
        "/favicon.ico",
    }
)


def _route_name(request: Request) -> str | None:
    endpoint = request.scope.get("endpoint")
    if endpoint is None:
        return None
    module = getattr(endpoint, "__module__", "")
    name = getattr(endpoint, "__name__", None)
    if not name:
        return None
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "app":
        return f"{parts[1]}.{name}"
    return name


def _content_length(response: Response | None) -> int | None:
    if response is None:
        return None
    value = response.headers.get("content-length")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to track requests with unique IDs."""

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:  # type: ignore[override]
        """Generate request ID and propagate through context."""
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        should_log_summary = request.url.path not in _SKIP_LOG_PATHS

        request_id_token = set_request_id(request_id)
        request.state.request_id = request_id
        if should_log_summary:
            begin_request_log_stats()

        started_at = perf_counter()
        status_code = 500
        response: Response | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id

            return response
        except Exception as exc:
            set_request_error(exc, error_type=exc.__class__.__name__)
            logger.exception(
                "Unhandled request middleware error",
                extra={"path": request.url.path, "request_id": request_id},
            )
            raise
        finally:
            if should_log_summary:
                duration_ms = (perf_counter() - started_at) * 1000
                set_request_summary_context(
                    method=request.method,
                    path=request.url.path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    route=_route_name(request),
                    response_content_length=_content_length(response),
                    client_ip=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    referer=request.headers.get("referer"),
                )

                if not has_request_db_activity():
                    log_request_summary(
                        logger,
                        service="binder-billing-crm",
                        env=settings.APP_ENV,
                        slow_request_ms=settings.LOG_SLOW_REQUEST_MS,
                        slow_query_ms=settings.LOG_SLOW_QUERY_MS,
                        high_query_count=settings.LOG_HIGH_QUERY_COUNT,
                    )
                    clear_request_log_stats()
                    reset_request_id(request_id_token)
            else:
                reset_request_id(request_id_token)
