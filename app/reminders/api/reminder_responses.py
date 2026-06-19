"""Shared OpenAPI error-response docs for reminders routes."""

from app.core.openapi_responses import (
    bad_request_response,
    conflict_response,
    error_responses,
    forbidden_response,
    not_found_response,
)

REMINDER_CREATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני התזכורת אינם תקינים"),
)

REMINDER_CANCEL_RESPONSES = error_responses(
    not_found_response(description="התזכורת המבוקשת לא נמצאה"),
    forbidden_response(description="אין הרשאה לביצוע הפעולה"),
    conflict_response(description="לא ניתן לבטל תזכורת שכבר נשלחה או בוטלה"),
)

REMINDER_DETAIL_RESPONSES = error_responses(
    not_found_response(description="התזכורת המבוקשת לא נמצאה"),
    forbidden_response(description="אין הרשאה לצפייה בתזכורת"),
)
