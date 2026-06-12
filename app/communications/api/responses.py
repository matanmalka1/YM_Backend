"""Shared OpenAPI error-response docs for correspondence routes."""

from app.core.openapi_responses import (
    bad_request_response,
    error_responses,
    not_found_response,
)

CORRESPONDENCE_CREATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני ההתכתבות אינם תקינים"),
    not_found_response(description="הלקוח המבוקש לא נמצא"),
)

CORRESPONDENCE_UPDATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני עדכון ההתכתבות אינם תקינים"),
    not_found_response(description="רשומת ההתכתבות המבוקשת לא נמצאה"),
)
