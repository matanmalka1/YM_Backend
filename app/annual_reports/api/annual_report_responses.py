"""Shared OpenAPI error-response docs for annual-report routes ."""

from app.core.openapi_responses import (
    bad_request_response,
    conflict_response,
    error_responses,
    not_found_response,
)

REPORT_CREATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני הדוח אינם תקינים"),
    conflict_response(description="כבר קיים דוח לשנת המס ולישות אלה"),
)

# status / submit / transition: invalid input, missing report, or illegal move.
REPORT_TRANSITION_RESPONSES = error_responses(
    bad_request_response(description="המעבר המבוקש אינו חוקי"),
    not_found_response(description="הדוח המבוקש לא נמצא"),
    conflict_response(description="מצב הדוח אינו מאפשר את המעבר"),
)

# Single-report writes that are not status transitions.
REPORT_UPDATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני עדכון הדוח אינם תקינים או שהדוח הוגש ונעול"),
    not_found_response(description="הדוח המבוקש לא נמצא"),
)

REPORT_TAX_CALCULATION_RESPONSES = error_responses(
    bad_request_response(description="נתוני חישוב המס אינם תקינים או שהדוח הוגש ונעול"),
    not_found_response(description="הדוח המבוקש לא נמצא"),
)

# Income / expense / annex line writes.
REPORT_LINE_WRITE_RESPONSES = error_responses(
    bad_request_response(description="נתוני השורה אינם תקינים או שהדוח הוגש ונעול"),
    not_found_response(description="הדוח המבוקש לא נמצא"),
)

REPORT_SCHEDULE_WRITE_RESPONSES = error_responses(
    bad_request_response(description="נתוני הנספח אינם תקינים או שהדוח הוגש ונעול"),
    not_found_response(description="הדוח המבוקש לא נמצא"),
)

REPORT_DELETE_RESPONSES = error_responses(
    bad_request_response(description="דוח שהוגש נעול ואינו ניתן למחיקה"),
    not_found_response(description="הדוח המבוקש לא נמצא"),
)
