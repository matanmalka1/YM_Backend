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

VAT_WORK_ITEM_MUTATION_RESPONSES = error_responses(
    bad_request_response(description='לא ניתן לעדכן או למחוק פריט עבודה למע"מ במצב הנוכחי'),
    not_found_response(description='פריט עבודה למע"מ לא נמצא'),
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
