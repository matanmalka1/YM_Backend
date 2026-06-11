"""FastAPI exception handler registration and implementations."""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    AppError,
    _request_id,
    contains_hebrew,
    error_response,
    http_error_code_for_status,
    http_error_message_for_status,
    validation_error_details,
)
from app.core.logging_config import get_logger, set_request_error

logger = get_logger(__name__)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    logger.warning(
        f"HTTP exception: {exc.status_code} - {exc.detail}",
        extra={"path": request.url.path},
    )
    if isinstance(exc.detail, dict) and {"code", "message", "details"}.intersection(exc.detail):
        raw_code = exc.detail.get("code")
        raw_message = exc.detail.get("message")
        return error_response(
            code=raw_code if isinstance(raw_code, str) else http_error_code_for_status(exc.status_code),
            message=(
                raw_message
                if isinstance(raw_message, str)
                else http_error_message_for_status(exc.status_code)
            ),
            details=exc.detail.get("details"),
            request_id=_request_id(request),
            status_code=exc.status_code,
        )

    code = http_error_code_for_status(exc.status_code)
    if isinstance(exc.detail, str) and contains_hebrew(exc.detail):
        message = exc.detail
    else:
        message = http_error_message_for_status(exc.status_code)
    return error_response(
        code=code,
        message=message,
        details=None,
        request_id=_request_id(request),
        status_code=exc.status_code,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.warning(
        f"Validation error: {exc.errors()}",
        extra={"path": request.url.path},
    )
    details = validation_error_details(exc.errors())
    return error_response(
        code="validation_error",
        message="חלק מהשדות אינם תקינים",
        details=details,
        request_id=_request_id(request),
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


async def database_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    set_request_error(exc, error_type="database_error")
    logger.error(
        "Database error occurred",
        exc_info=exc,
        extra={"path": request.url.path},
    )
    return error_response(
        code="internal_server_error",
        message="אירעה שגיאה לא צפויה",
        details=None,
        request_id=_request_id(request),
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    set_request_error(exc, error_type="internal_server_error")
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        extra={"path": request.url.path},
    )
    return error_response(
        code="internal_server_error",
        message="אירעה שגיאה לא צפויה",
        details=None,
        request_id=_request_id(request),
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    if exc.status_code >= 500:
        set_request_error(exc, error_type=exc.code)
    return error_response(
        code=exc.code,
        message=exc.message,
        details=exc.details,
        request_id=_request_id(request),
        status_code=exc.status_code,
    )


async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    msg = str(exc)
    message = msg if (msg and contains_hebrew(msg)) else "הבקשה אינה תקינה"
    return error_response(
        code="bad_request",
        message=message,
        details=None,
        request_id=_request_id(request),
        status_code=status.HTTP_400_BAD_REQUEST,
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers in one place."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(SQLAlchemyError, database_exception_handler)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(ValueError, value_error_handler)
    app.add_exception_handler(Exception, general_exception_handler)
