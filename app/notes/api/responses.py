"""Shared OpenAPI error-response docs for note routes (entity + business)."""

from app.core.openapi_responses import (
    bad_request_response,
    error_responses,
    not_found_response,
)

ENTITY_NOTE_CREATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני ההערה אינם תקינים"),
    not_found_response(description="הלקוח המבוקש לא נמצא"),
)

BUSINESS_NOTE_CREATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני ההערה אינם תקינים"),
    not_found_response(description="העסק המבוקש לא נמצא"),
)

NOTE_UPDATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני עדכון ההערה אינם תקינים"),
    not_found_response(description="ההערה המבוקשת לא נמצאה"),
)
