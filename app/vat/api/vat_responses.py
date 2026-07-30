"""Shared OpenAPI error-response docs for VAT routes ."""

from app.core.openapi_responses import (
    bad_request_response,
    conflict_response,
    error_responses,
    not_found_response,
)

VAT_WORK_ITEM_CREATE_RESPONSES = error_responses(
    bad_request_response(description='נתוני פריט העבודה למע"מ אינם תקינים'),
    conflict_response(description="כבר קיים פריט עבודה לעסק ולתקופה אלה"),
)

# Status transitions on an existing work item: bad input, missing item, or an
# illegal transition for the current state.
VAT_WORK_ITEM_TRANSITION_RESPONSES = error_responses(
    bad_request_response(description="לא ניתן לבצע את המעבר במצב הנוכחי"),
    not_found_response(description='פריט עבודה למע"מ לא נמצא'),
    conflict_response(description="מעבר הסטטוס אינו חוקי במצב הנוכחי"),
)

# Creating an amendment: the original must exist, be closed, and not already
# have one (§4.1.6).
VAT_WORK_ITEM_AMEND_RESPONSES = error_responses(
    bad_request_response(description="ניתן לתקן רק פריט שהוגש"),
    not_found_response(description='פריט עבודה למע"מ לא נמצא'),
    conflict_response(description="לפריט זה כבר קיים תיקון"),
)

VAT_WORK_ITEM_MUTATION_RESPONSES = error_responses(
    bad_request_response(description='לא ניתן לעדכן או למחוק פריט עבודה למע"מ במצב הנוכחי'),
    not_found_response(description='פריט עבודה למע"מ לא נמצא'),
)

# Deleting carries one conflict the metadata PATCH cannot: an amendment is a link
# in a chain and removing it would hide the record it corrects (D-12).
VAT_WORK_ITEM_DELETE_RESPONSES = error_responses(
    VAT_WORK_ITEM_MUTATION_RESPONSES,
    conflict_response(description="לא ניתן למחוק רשומת תיקון — יש לבטל אותה"),
)

# Withdrawing a correction: the target must be an amendment, must still be open,
# and must be the tip of its chain (D-12).
VAT_WORK_ITEM_WITHDRAW_RESPONSES = error_responses(
    bad_request_response(description="הרשומה אינה רשומת תיקון, או שהיא כבר הוגשה"),
    not_found_response(description='פריט עבודה למע"מ לא נמצא'),
    conflict_response(description="לרשומת התיקון עצמה כבר קיים תיקון"),
)

VAT_INVOICE_CREATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני החשבונית אינם תקינים"),
    not_found_response(description='פריט עבודה למע"מ לא נמצא'),
    conflict_response(description="לא ניתן להוסיף חשבונית במצב הנוכחי"),
)

VAT_INVOICE_UPDATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני החשבונית אינם תקינים"),
    not_found_response(description="החשבונית המבוקשת לא נמצאה"),
    conflict_response(description="לא ניתן לעדכן חשבונית לאחר הגשה"),
)

VAT_INVOICE_DELETE_RESPONSES = error_responses(
    bad_request_response(description="לא ניתן למחוק חשבונית במצב הנוכחי"),
    not_found_response(description="החשבונית המבוקשת לא נמצאה"),
)
