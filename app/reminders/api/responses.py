"""Shared OpenAPI error-response docs for reminders routes."""

from app.core.openapi_responses import (
    bad_request_response,
    conflict_response,
    error_responses,
    not_found_response,
)

REMINDER_CREATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני התזכורת אינם תקינים"),
)

REMINDER_CANCEL_RESPONSES = error_responses(
    not_found_response(description="התזכורת המבוקשת לא נמצאה"),
    conflict_response(description="לא ניתן לבטל תזכורת שכבר נשלחה או בוטלה"),
)
