"""Configuration for route audit scripts.

Edit this file to maintain exceptions and known patterns across:
  - check_role_coverage.py
  - check_missing_pagination.py
  - check_unused_routes.py
  - check_enum_sync.py
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Routes that are intentionally public (no require_role needed)
# Used by: check_role_coverage.py
# ---------------------------------------------------------------------------

PUBLIC_ROUTES: set[tuple[str, str]] = {
    # method, full path (exact match, FastAPI path params allowed)
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/info"),
    ("GET", "/ready"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/refresh"),
    ("GET", "/api/v1/auth/me"),
    ("POST", "/api/v1/auth/forgot-password"),
    ("POST", "/api/v1/auth/reset-password"),
    # Public signer flow — no auth (FastAPI param name is {token})
    ("GET", "/sign/{token}"),
    ("POST", "/sign/{token}/approve"),
    ("POST", "/sign/{token}/decline"),
    # OpenAPI / docs (FastAPI built-ins, all HTTP methods)
    ("GET", "/docs"),
    ("HEAD", "/docs"),
    ("GET", "/redoc"),
    ("HEAD", "/redoc"),
    ("GET", "/openapi.json"),
    ("HEAD", "/openapi.json"),
    ("GET", "/docs/oauth2-redirect"),
    ("HEAD", "/docs/oauth2-redirect"),
}

# Routes where get_current_user is enough (no role restriction needed)
# These still require a valid JWT but don't restrict by role.
AUTH_ONLY_ROUTES: set[tuple[str, str]] = set()


# ---------------------------------------------------------------------------
# List endpoints that intentionally have no pagination
# Used by: check_missing_pagination.py
# Format: (method, path_pattern) — path_pattern matched with normalize_path()
# ---------------------------------------------------------------------------

NO_PAGINATION_EXCEPTIONS: set[tuple[str, str]] = {
    # Summary / stats / aggregate endpoints
    ("GET", "/api/v1/dashboard"),
    ("GET", "/api/v1/dashboard/tax-submissions"),
    ("GET", "/api/v1/dashboard/work-overview"),
    ("GET", "/api/v1/vat/work-items/status-summary"),
    ("GET", "/api/v1/vat/work-items/groups"),
    ("GET", "/api/v1/vat/clients/{param}/summary"),
    ("GET", "/api/v1/annual-reports/tax-preview"),
    ("GET", "/api/v1/tax-year/active/summary"),
    ("GET", "/api/v1/tax-year/{param}/summary"),
    # Bounded domain option lists
    ("GET", "/api/v1/vat/clients/{param}/period-options"),
    ("GET", "/api/v1/tax-calendar"),
    ("GET", "/api/v1/clients/sidebar"),
    # Exports / downloads
    ("GET", "/api/v1/clients/export"),
    ("GET", "/api/v1/vat/clients/{param}/export"),
    ("GET", "/api/v1/annual-reports/{param}/export/pdf"),
    # Single-entity sub-resources that return bounded lists
    ("GET", "/api/v1/annual-reports/{param}/schedules"),
    ("GET", "/api/v1/annual-reports/{param}/history"),
    ("GET", "/api/v1/annual-reports/{param}/financials"),
    ("GET", "/api/v1/annual-reports/{param}/readiness"),
    ("GET", "/api/v1/annual-reports/{param}/tax-calculation"),
    ("GET", "/api/v1/annual-reports/{param}/advances-summary"),
    ("GET", "/api/v1/annual-reports/{param}/income"),
    ("GET", "/api/v1/annual-reports/{param}/expenses"),
    ("GET", "/api/v1/annual-reports/{param}/status"),
    ("GET", "/api/v1/signature-requests/pending"),
    ("GET", "/api/v1/binders/open"),
    ("GET", "/api/v1/work-queue"),
    ("GET", "/api/v1/binders/{param}/intakes"),
    ("GET", "/api/v1/vat/work-items/{param}/invoices"),
    ("GET", "/api/v1/reports/vat-compliance"),
    ("GET", "/api/v1/reports/advance-payments"),
    ("GET", "/api/v1/reports/annual-reports"),
    ("GET", "/api/v1/reports/aging"),
    ("GET", "/api/v1/settings/tax-calendar/rules"),
    ("GET", "/api/v1/settings/tax-calendar/entries"),
    ("GET", "/api/v1/advance-payments/overview/batches"),
    # Health / meta
    ("GET", "/health"),
    ("GET", "/info"),
    ("GET", "/"),
    # Auth
    ("GET", "/api/v1/auth/me"),
}

# Path suffixes that indicate a non-list endpoint regardless of params
NON_LIST_SUFFIXES: tuple[str, ...] = (
    "/summary",
    "/status",
    "/status-card",
    "/overview",
    "/export",
    "/export/pdf",
    "/template",
    "/import",
    "/preview-impact",
    "/conflict/{param}",
    "/readiness",
    "/financials",
    "/tax-calculation",
    "/advances-summary",
    "/audit",
    "/history",
    "/lookup",
    "/me",
    "/health",
    "/info",
    "/default",
    "/sidebar",
    "/groups",
    "/details",
    "/download-url",
    "/signals",
    "/versions",
    "/prefill-turnover",
    "/kpi",
    "/deadline",
    "/amend",
    "/transition",
    "/rules",
    "/entries",
    "/period-options",
    "/default-rules",
)


# ---------------------------------------------------------------------------
# Routes that are known to be used externally or manually
# Used by: check_unused_routes.py
# ---------------------------------------------------------------------------

KNOWN_EXTERNAL_OR_MANUAL_ROUTES: set[tuple[str, str]] = {
    # Public signer flow (opened via link, not frontend JS)
    ("GET", "/sign/{signing_token}"),
    ("POST", "/sign/{signing_token}/approve"),
    ("POST", "/sign/{signing_token}/decline"),
    # Health / infra (called by Render, uptime monitors)
    ("GET", "/health"),
    ("GET", "/ready"),
    ("GET", "/info"),
    ("GET", "/"),
    # OpenAPI
    ("GET", "/openapi.json"),
    ("GET", "/docs"),
    ("GET", "/redoc"),
    # Excel imports/exports (browser download, not axios)
    ("GET", "/api/v1/clients/export"),
    ("GET", "/api/v1/clients/template"),
    ("POST", "/api/v1/clients/import"),
}


# ---------------------------------------------------------------------------
# Enum sync map: Python enum class name → frontend constants file + array name
# Used by: check_enum_sync.py
# Format: "PythonEnumName": "relative/path/from/frontend/src:ARRAY_NAME"
# ---------------------------------------------------------------------------

ENUM_SYNC_MAP: dict[str, str] = {
    "ClientStatus": "features/clients/constants.ts:CLIENT_STATUSES",
    "EntityType": "features/clients/constants.ts:ENTITY_TYPES",
    "IdNumberType": "features/clients/constants.ts:CLIENT_ID_NUMBER_TYPES",
    "VatType": "features/clients/constants.ts:VAT_TYPES",
    "VatWorkItemStatus": "features/vatReports/constants.ts:VAT_WORK_ITEM_STATUS_VALUES",
    "VatRateType": "features/vatReports/constants.ts:VAT_RATE_TYPE_VALUES",
    # DocumentType exists in two Python modules with different values.
    # Use module-qualified keys: "module.ClassName"
    "app.vat_reports.models.vat_enums.DocumentType": "features/vatReports/constants.ts:VAT_DOCUMENT_TYPE_VALUES",
    "app.permanent_documents.models.permanent_document.PermanentDocumentType": "features/documents/documents.constants.ts:DOCUMENT_TYPES",
    "ChargeStatus": "features/charges/constants.ts:CHARGE_STATUS_VALUES",
    "ChargeType": "features/charges/constants.ts:CHARGE_TYPE_VALUES",
    "UserRole": "features/users/constants.ts:USER_ROLE_VALUES",
    "SignatureRequestStatus": "features/signatureRequests/constants.ts:SIGNATURE_REQUEST_STATUS_VALUES",
    "SignatureRequestType": "features/signatureRequests/constants.ts:SIGNATURE_REQUEST_TYPE_VALUES",
    "ContactType": "features/authorityContacts/api/contracts.ts:AUTHORITY_CONTACT_TYPE_VALUES",
    "SubmissionMethod": "features/annualReports/report.constants.ts:REPORT_SUBMISSION_METHODS",
    "NotificationTrigger": "features/notifications/api/contracts.ts:NOTIFICATION_TRIGGER_VALUES",
}

# Enums intentionally not in frontend (internal/DB-only)
ENUM_BACKEND_ONLY: set[str] = {
    "DeadlineRuleType",
    "ObligationType",
    "AdvancePaymentFrequency",
    "WorkQueueSourceType",
    "AuditAction",
    "AuditStatus",
    "IdempotencyStatus",
    "ReminderStatus",
    "ReminderActionType",
    "PersonLegalEntityRole",
    "DocumentScope",
    "DocumentStatus",
    # DocumentType exists in two Python modules with different values;
    # the permanent_documents one is backend-only (used in permanent_documents feature, mapped manually)
    "DocumentType",
    # These exist in frontend but aren't simple _VALUES arrays — handled in feature-specific code
    "BusinessStatus",
    "TaskStatus",
    "TaskPriority",
    "NotificationChannel",
    "NotificationStatus",
    "CounterpartyIdType",
    "ExpenseCategory",
    "InvoiceType",
}
