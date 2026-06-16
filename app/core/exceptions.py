"""
Centralized exception handling for production safety.

Provides:
- Consistent error envelope
- No stack trace leaks in responses
- Proper error logging with traces
"""

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.error_codes import ErrorCode
from app.core.logging_config import get_request_id

REQUEST_LOC_PREFIXES = {"body", "query", "path", "header", "cookie"}


class ErrorBody(BaseModel):
    """Body of the standard application error envelope."""

    code: str
    message: str
    details: Any = None
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    """Standard application error envelope: ``{"error": {...}}``.

    Used as the ``response_model`` for documented error responses such as 404.
    """

    error: ErrorBody


_HTTP_CODE_MAP: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_server_error",
}

_HTTP_MESSAGE_MAP: dict[int, str] = {
    400: "הבקשה אינה תקינה",
    401: "נדרש אימות",
    403: "אין הרשאה לביצוע הפעולה",
    404: "המשאב לא נמצא",
    405: "שיטת הבקשה אינה נתמכת",
    409: "הבקשה מתנגשת עם מצב קיים",
    422: "חלק מהשדות אינם תקינים",
    429: "בוצעו יותר מדי בקשות",
    500: "אירעה שגיאה לא צפויה",
}


def http_error_code_for_status(status_code: int) -> str:
    if status_code in _HTTP_CODE_MAP:
        return _HTTP_CODE_MAP[status_code]
    if 400 <= status_code < 500:
        return "request_error"
    return "internal_server_error"


def http_error_message_for_status(status_code: int) -> str:
    if status_code in _HTTP_MESSAGE_MAP:
        return _HTTP_MESSAGE_MAP[status_code]
    if 400 <= status_code < 500:
        return "הבקשה אינה תקינה"
    return "אירעה שגיאה לא צפויה"


def contains_hebrew(s: str) -> bool:
    return any("\u0590" <= ch <= "\u05ff" for ch in s)


def _field_path(loc: tuple) -> str:
    parts = [str(p) for p in loc]
    if parts and parts[0] in REQUEST_LOC_PREFIXES:
        parts = parts[1:]
    return ".".join(parts)


def _request_id(request: Request) -> str | None:
    rid = getattr(request.state, "request_id", None)
    if rid is not None:
        return rid
    return get_request_id()


def validation_error_details(errors: list[dict]) -> list[dict]:
    result = []
    for err in errors:
        result.append(
            {
                "field": _field_path(err.get("loc", ())),
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
        )
    return result


def error_response(
    *,
    code: str,
    message: str,
    details: Any = None,
    request_id: str | None = None,
    status_code: int,
) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }
    if request_id is not None:
        body["error"]["request_id"] = request_id
    return JSONResponse(status_code=status_code, content=body)


# ── Application-level domain errors ─────────────────────────────────────────


class AppError(Exception):
    def __init__(
        self, message: str, code: ErrorCode, status_code: int = 400, details: Any = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


class NotFoundError(AppError):
    def __init__(self, message: str, code: ErrorCode):
        super().__init__(message, code, status_code=404)


class ConflictError(AppError):
    def __init__(self, message: str, code: ErrorCode):
        super().__init__(message, code, status_code=409)


class ForbiddenError(AppError):
    def __init__(self, message: str, code: ErrorCode):
        super().__init__(message, code, status_code=403)
