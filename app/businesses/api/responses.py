"""Shared OpenAPI error-response docs for business routes ."""

from app.core.openapi_responses import (
    bad_request_response,
    conflict_response,
    error_responses,
    not_found_response,
)

BUSINESS_CREATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני העסק אינם תקינים"),
    not_found_response(description="הלקוח המבוקש לא נמצא"),
    conflict_response(description="כבר קיים עסק תואם ללקוח זה"),
)

BUSINESS_UPDATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני עדכון העסק אינם תקינים"),
    not_found_response(description="העסק המבוקש לא נמצא"),
    conflict_response(description="לא ניתן לעדכן את העסק במצב הנוכחי"),
)

# delete / restore share the same not-found + conflict shape.
BUSINESS_ACTION_RESPONSES = error_responses(
    not_found_response(description="העסק המבוקש לא נמצא"),
    conflict_response(description="לא ניתן לבצע את הפעולה על העסק במצב הנוכחי"),
)
