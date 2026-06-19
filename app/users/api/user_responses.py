"""Shared OpenAPI error-response docs for user-management routes."""

from app.core.openapi_responses import (
    bad_request_response,
    conflict_response,
    error_responses,
    not_found_response,
)

USER_CREATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני המשתמש אינם תקינים"),
    conflict_response(description='כבר קיים משתמש עם כתובת דוא"ל זו'),
)

USER_UPDATE_RESPONSES = error_responses(
    bad_request_response(description="נתוני עדכון המשתמש אינם תקינים"),
    not_found_response(description="המשתמש המבוקש לא נמצא"),
    conflict_response(description='כבר קיים משתמש עם כתובת דוא"ל זו'),
)

USER_ACTIVATE_RESPONSES = error_responses(
    not_found_response(description="המשתמש המבוקש לא נמצא"),
    conflict_response(description="המשתמש כבר פעיל"),
)

USER_DEACTIVATE_RESPONSES = error_responses(
    not_found_response(description="המשתמש המבוקש לא נמצא"),
    conflict_response(description="המשתמש כבר מושבת"),
)

USER_RESET_PASSWORD_RESPONSES = error_responses(
    bad_request_response(description="הסיסמה החדשה אינה תקינה"),
    not_found_response(description="המשתמש המבוקש לא נמצא"),
)
