"""
Entity type and action constants for the generic audit log.

Use these constants in service code — never raw strings.
"""

# Entity types
ENTITY_BUSINESS = "business"
ENTITY_CLIENT = "client"
ENTITY_CHARGE = "charge"
ENTITY_ANNUAL_REPORT = "annual_report"

ALLOWED_READ_ENTITY_TYPES = {
    ENTITY_ANNUAL_REPORT,
    ENTITY_BUSINESS,
    ENTITY_CHARGE,
    ENTITY_CLIENT,
}

INVALID_ENTITY_TYPE_ERROR = "סוג ישות לא נתמך להיסטוריית שינויים"
ENTITY_NOT_FOUND_ERROR = "הישות המבוקשת לא נמצאה"

# Shared actions
ACTION_CREATED = "created"
ACTION_UPDATED = "updated"
ACTION_DELETED = "deleted"
ACTION_RESTORED = "restored"
ACTION_ENTITY_TYPE_CHANGED = "entity_type_changed"

# Charge-specific status transitions
ACTION_ISSUED = "issued"
ACTION_PAID = "paid"
ACTION_CANCELED = "canceled"

# Annual report status transition
ACTION_STATUS_CHANGED = "status_changed"
ACTION_ANNUAL_REPORT_DETAIL_UPDATED = "annual_report_detail_updated"
ACTION_ANNUAL_REPORT_DEADLINE_UPDATED = "annual_report_deadline_updated"
ACTION_ANNEX_LINE_ADDED = "annex_line_added"
ACTION_ANNEX_LINE_UPDATED = "annex_line_updated"
ACTION_ANNEX_LINE_DELETED = "annex_line_deleted"

# Annual report financial lines
ACTION_INCOME_ADDED = "income_added"
ACTION_INCOME_UPDATED = "income_updated"
ACTION_INCOME_DELETED = "income_deleted"
ACTION_EXPENSE_ADDED = "expense_added"
ACTION_EXPENSE_UPDATED = "expense_updated"
ACTION_EXPENSE_DELETED = "expense_deleted"
