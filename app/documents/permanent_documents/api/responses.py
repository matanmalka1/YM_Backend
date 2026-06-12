"""Shared OpenAPI error-response docs for permanent-document routes."""

from app.core.openapi_responses import (
    bad_request_response,
    error_responses,
    internal_server_error_response,
    not_found_response,
)

DOCUMENT_UPLOAD_RESPONSES = error_responses(
    bad_request_response(description="נתוני המסמך אינם תקינים"),
    internal_server_error_response(description="העלאת הקובץ לאחסון נכשלה"),
)

DOCUMENT_REPLACE_RESPONSES = error_responses(
    bad_request_response(description="נתוני החלפת המסמך אינם תקינים"),
    not_found_response(description="המסמך המבוקש לא נמצא"),
    internal_server_error_response(description="העלאת הקובץ לאחסון נכשלה"),
)

DOCUMENT_DELETE_RESPONSES = error_responses(
    bad_request_response(description="לא ניתן למחוק את המסמך במצב הנוכחי"),
    not_found_response(description="המסמך המבוקש לא נמצא"),
)
