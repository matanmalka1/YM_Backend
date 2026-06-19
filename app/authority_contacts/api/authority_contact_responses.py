"""Shared OpenAPI error-response docs for authority_contacts routes."""

from app.core.openapi_responses import (
    bad_request_response,
    error_responses,
    not_found_response,
)

AUTHORITY_CONTACT_CREATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני איש הקשר אינם תקינים"),
    not_found_response(description="הלקוח המבוקש לא נמצא"),
)

AUTHORITY_CONTACT_UPDATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני עדכון איש הקשר אינם תקינים"),
    not_found_response(description="איש הקשר המבוקש לא נמצא"),
)
