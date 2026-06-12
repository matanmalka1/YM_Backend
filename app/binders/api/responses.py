"""Shared OpenAPI error-response docs for binder routes ."""

from app.core.openapi_responses import (
    bad_request_response,
    error_responses,
    not_found_response,
)

# Lifecycle action on an existing binder (mark-full, receive-material, handover,
# revert, etc.): invalid state or missing binder.
BINDER_ACTION_RESPONSES = error_responses(
    bad_request_response(description="לא ניתן לבצע את הפעולה על הקלסר במצב הנוכחי"),
    not_found_response(description="הקלסר המבוקש לא נמצא"),
)

BINDER_RECEIVE_RESPONSES = error_responses(
    bad_request_response(description="נתוני קליטת הקלסר אינם תקינים"),
)

BINDER_READY_BULK_RESPONSES = error_responses(
    bad_request_response(description="לא ניתן לסמן מוכן למסירה במצב הנוכחי"),
)

BINDER_HANDOVER_BULK_RESPONSES = error_responses(
    bad_request_response(description="נתוני המסירה ללקוח אינם תקינים"),
)

BINDER_INTAKE_UPDATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני עדכון הקליטה אינם תקינים"),
    not_found_response(description="הקלסר המבוקש לא נמצא"),
)
