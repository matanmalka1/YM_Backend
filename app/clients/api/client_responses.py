"""Shared OpenAPI error-response docs for client routes ."""

from app.core.openapi_responses import (
    bad_request_response,
    conflict_response,
    error_responses,
    not_found_response,
)

CLIENT_CREATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני הלקוח אינם תקינים"),
    conflict_response(description="כבר קיים לקוח עם מזהה זה"),
)

CLIENT_PREVIEW_RESPONSES = error_responses(
    bad_request_response(description="נתוני הלקוח אינם תקינים"),
)

CLIENT_UPDATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני עדכון הלקוח אינם תקינים"),
    not_found_response(description="הלקוח המבוקש לא נמצא"),
    conflict_response(description="לא ניתן לעדכן את הלקוח במצב הנוכחי"),
)

# delete / restore share the same not-found + conflict shape.
CLIENT_ACTION_RESPONSES = error_responses(
    not_found_response(description="הלקוח המבוקש לא נמצא"),
    conflict_response(description="לא ניתן לבצע את הפעולה על הלקוח במצב הנוכחי"),
)
