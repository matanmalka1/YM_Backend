"""Shared OpenAPI error-response docs for advance_payments routes."""

from app.core.openapi_responses import (
    bad_request_response,
    conflict_response,
    error_responses,
    not_found_response,
)

ADVANCE_PAYMENT_CREATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני המקדמה אינם תקינים"),
    not_found_response(description="הלקוח המבוקש לא נמצא"),
    conflict_response(description="תדירות או תקופת המקדמה אינן נתמכות"),
)

ADVANCE_PAYMENT_GENERATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני יצירת לוח המקדמות אינם תקינים"),
    not_found_response(description="הלקוח המבוקש לא נמצא"),
    conflict_response(description="לא ניתן ליצור לוח מקדמות במצב הנוכחי"),
)

ADVANCE_PAYMENT_UPDATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני עדכון המקדמה אינם תקינים"),
    not_found_response(description="תשלום המקדמה המבוקש לא נמצא"),
    conflict_response(description="לא ניתן לעדכן את המקדמה במצב הנוכחי"),
)
