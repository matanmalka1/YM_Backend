"""Shared OpenAPI error-response docs for charge routes.

401/403 are documented globally by build_openapi for authenticated/role-gated
routes, so they are not repeated here.
"""

from app.core.openapi_responses import (
    bad_request_response,
    conflict_response,
    error_responses,
    internal_server_error_response,
    not_found_response,
)

CHARGE_CREATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני החיוב אינם תקינים"),
    internal_server_error_response(),
)

CHARGE_UPDATE_RESPONSES = error_responses(
    bad_request_response(description="לא ניתן לערוך חיוב שאינו במצב טיוטה"),
    not_found_response(description="החיוב המבוקש לא נמצא"),
)

CHARGE_CANCEL_RESPONSES = error_responses(
    bad_request_response(description="לא ניתן לבטל חיוב במצב הנוכחי"),
    not_found_response(description="החיוב המבוקש לא נמצא"),
    conflict_response(description="החיוב כבר בוטל"),
)
