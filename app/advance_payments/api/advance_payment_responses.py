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
    conflict_response(
        description="תדירות או תקופת המקדמה אינן נתמכות, או שתיק הלקוח סגור או מוקפא"
    ),
)

ADVANCE_PAYMENT_GENERATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני יצירת לוח המקדמות אינם תקינים"),
    not_found_response(description="הלקוח המבוקש לא נמצא"),
    conflict_response(
        description="לא ניתן ליצור לוח מקדמות במצב הנוכחי, או שתיק הלקוח סגור או מוקפא"
    ),
)

ADVANCE_PAYMENT_REFRESH_TURNOVER_RESPONSES = error_responses(
    not_found_response(description="תשלום המקדמה או דוח מע״מ לתקופה לא נמצאו"),
    conflict_response(description="דוח המע״מ לתקופה טרם הוגש"),
)

# Bulk mark-paid reports unpayable rows as skips, so it has no 404/409.
ADVANCE_PAYMENT_BULK_MARK_PAID_RESPONSES = error_responses(
    bad_request_response(description="רשימת המקדמות אינה תקינה"),
)

# Office-wide generation reports per-client problems inside the body (failed /
# ineligible), so a client that cannot be generated for is not a 404 or a 409.
ADVANCE_PAYMENT_BULK_GENERATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני יצירת לוחות המקדמות אינם תקינים"),
)

# Bulk refresh reports unsnapshottable periods as counts, so it has no 409 —
# an unfiled return is a skip, not a conflict.
ADVANCE_PAYMENT_BULK_REFRESH_TURNOVER_RESPONSES = error_responses(
    bad_request_response(description="רשימת המקדמות אינה תקינה"),
    not_found_response(description="אחת המקדמות המבוקשות לא נמצאה עבור הלקוח"),
)

ADVANCE_PAYMENT_UPDATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני עדכון המקדמה אינם תקינים, או שהמקדמה סגורה"),
    not_found_response(description="תשלום המקדמה המבוקש לא נמצא"),
    conflict_response(description="לא ניתן לעדכן את המקדמה במצב הנוכחי"),
)

# The single-step ladder move (advisor only). 400 covers an invalid step, a
# backward move without a note, a locked record, and a close that fails the gate.
ADVANCE_PAYMENT_TRANSITION_RESPONSES = error_responses(
    bad_request_response(description="המעבר אינו חוקי, או שהמקדמה אינה מוכנה לסגירה"),
    not_found_response(description="תשלום המקדמה המבוקש לא נמצא"),
)

# Delete is refused on a closed period (D-13/D-22) — that refusal is the 400.
# Creating an amendment: the original must exist, be closed, and not already
# have one (§4.1.6).
ADVANCE_PAYMENT_AMEND_RESPONSES = error_responses(
    bad_request_response(description="ניתן לתקן רק מקדמה שנסגרה"),
    not_found_response(description="תשלום המקדמה המבוקש לא נמצא"),
    conflict_response(description="למקדמה זו כבר קיים תיקון"),
)

ADVANCE_PAYMENT_DELETE_RESPONSES = error_responses(
    bad_request_response(description="לא ניתן למחוק מקדמה סגורה"),
    not_found_response(description="תשלום המקדמה המבוקש לא נמצא"),
)
