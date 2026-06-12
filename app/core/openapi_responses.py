"""OpenAPI response-doc helpers for the standard error envelope."""

from typing import Any

from app.core.exceptions import ErrorEnvelope


def error_response_doc(status_code: int, *, description: str) -> dict[int, dict[str, Any]]:
    """OpenAPI ``responses=`` entry documenting an error with the standard envelope."""
    return {status_code: {"model": ErrorEnvelope, "description": description}}


def error_responses(*items: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Merge single-status error-response docs into one ``responses=`` mapping.

    Prefer this over ``{**a, **b}`` dict-spreads at the call site. For a pattern
    repeated within a domain, capture the result in a constant in that domain's
    ``api/responses.py`` (named by pattern, e.g. ``CLIENT_WRITE_RESPONSES``).
    """
    merged: dict[int, dict[str, Any]] = {}
    for item in items:
        merged.update(item)
    return merged


def bad_request_response(*, description: str = "הבקשה אינה תקינה") -> dict[int, dict[str, Any]]:
    return error_response_doc(400, description=description)


def unauthorized_response(*, description: str = "נדרש אימות") -> dict[int, dict[str, Any]]:
    return error_response_doc(401, description=description)


def forbidden_response(
    *, description: str = "אין הרשאה לביצוע הפעולה"
) -> dict[int, dict[str, Any]]:
    return error_response_doc(403, description=description)


def not_found_response(*, description: str = "המשאב לא נמצא") -> dict[int, dict[str, Any]]:
    return error_response_doc(404, description=description)


def conflict_response(
    *, description: str = "הבקשה מתנגשת עם מצב קיים"
) -> dict[int, dict[str, Any]]:
    return error_response_doc(409, description=description)


def internal_server_error_response(
    *, description: str = "אירעה שגיאה לא צפויה"
) -> dict[int, dict[str, Any]]:
    return error_response_doc(500, description=description)
