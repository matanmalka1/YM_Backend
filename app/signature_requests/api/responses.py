"""Shared OpenAPI error-response docs for signature_requests routes."""

from app.core.openapi_responses import (
    bad_request_response,
    conflict_response,
    error_responses,
    not_found_response,
)

SIGNATURE_CREATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני בקשת החתימה אינם תקינים"),
    not_found_response(description="הלקוח או העסק המבוקשים לא נמצאו"),
)

SIGNATURE_CANCEL_RESPONSES = error_responses(
    not_found_response(description="בקשת החתימה המבוקשת לא נמצאה"),
    conflict_response(description="לא ניתן לבטל את בקשת החתימה במצב הנוכחי"),
)
