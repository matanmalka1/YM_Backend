"""Shared OpenAPI error-response docs for task routes."""

from app.core.openapi_responses import (
    bad_request_response,
    conflict_response,
    error_responses,
    not_found_response,
)

TASK_CREATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני המשימה אינם תקינים"),
)

TASK_UPDATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני עדכון המשימה אינם תקינים"),
    not_found_response(description="המשימה המבוקשת לא נמצאה"),
    conflict_response(description="לא ניתן לערוך משימה שהושלמה או בוטלה"),
)

TASK_COMPLETE_RESPONSES = error_responses(
    not_found_response(description="המשימה המבוקשת לא נמצאה"),
    conflict_response(description="לא ניתן להשלים משימה שבוטלה או שכבר הושלמה"),
)

TASK_CANCEL_RESPONSES = error_responses(
    not_found_response(description="המשימה המבוקשת לא נמצאה"),
    conflict_response(description="לא ניתן לבטל משימה שהושלמה או שכבר בוטלה"),
)

TASK_BULK_COMPLETE_RESPONSES = error_responses(
    bad_request_response(description="נתוני הבקשה אינם תקינים"),
    conflict_response(description="מפתח אידמפוטנטיות בשימוש"),
)

TASK_BULK_ASSIGN_RESPONSES = error_responses(
    bad_request_response(description="נתוני הבקשה אינם תקינים"),
    not_found_response(description="המשתמש המשויך לא נמצא"),
    conflict_response(description="מפתח אידמפוטנטיות בשימוש"),
)
