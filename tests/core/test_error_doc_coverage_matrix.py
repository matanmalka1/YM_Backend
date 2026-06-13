"""#53 per-endpoint coverage: body-driven error statuses (400/409/500).

Source of truth: ``docs/architecture/error-doc-matrix.md``. This test encodes the
same matrix as a data table and asserts the live OpenAPI spec documents exactly
those 400/409/500 statuses per endpoint — no missing, no accidental extras.

401/403 are injected globally by ``build_openapi`` and covered by
``test_openapi_auth_error_docs.py``; 404 is covered by
``test_openapi_not_found_docs.py``. They are out of scope here.
"""

from app.main import app

_BODY_STATUSES = ("400", "409", "500")

# (METHOD, path) -> set of body-driven statuses the endpoint must document.
# Mirrors docs/architecture/error-doc-matrix.md. Endpoints not listed must not
# document any of 400/409/500.
_EXPECTED: dict[tuple[str, str], set[str]] = {
    # vat
    ("POST", "/api/v1/vat/work-items"): {"400", "409"},
    ("POST", "/api/v1/vat/work-items/{item_id}/file"): {"400", "409"},
    ("POST", "/api/v1/vat/work-items/{item_id}/invoices"): {"400", "409"},
    ("PATCH", "/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}"): {"400", "409"},
    ("DELETE", "/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}"): {"400"},
    ("POST", "/api/v1/vat/work-items/{item_id}/materials-complete"): {"400", "409"},
    ("POST", "/api/v1/vat/work-items/{item_id}/ready-for-review"): {"400", "409"},
    ("POST", "/api/v1/vat/work-items/{item_id}/send-back"): {"400", "409"},
    # binders
    ("POST", "/api/v1/binders/receive"): {"400"},
    ("POST", "/api/v1/binders/handover-to-client-bulk"): {"400"},
    ("POST", "/api/v1/binders/mark-ready-for-handover-bulk"): {"400"},
    ("POST", "/api/v1/binders/{binder_id}/handover-to-client"): {"400"},
    ("POST", "/api/v1/binders/{binder_id}/mark-full"): {"400"},
    ("POST", "/api/v1/binders/{binder_id}/mark-ready-for-handover"): {"400"},
    ("POST", "/api/v1/binders/{binder_id}/receive-material"): {"400"},
    ("POST", "/api/v1/binders/{binder_id}/reopen-capacity"): {"400"},
    ("POST", "/api/v1/binders/{binder_id}/revert-ready-for-handover"): {"400"},
    ("PATCH", "/api/v1/binders/{binder_id}/intakes/{intake_id}"): {"400"},
    # annual_reports
    ("POST", "/api/v1/annual-reports"): {"400", "409"},
    ("POST", "/api/v1/annual-reports/{report_id}/amend"): {"400", "409"},
    ("POST", "/api/v1/annual-reports/{report_id}/status"): {"400", "409"},
    ("POST", "/api/v1/annual-reports/{report_id}/submit"): {"400", "409"},
    ("POST", "/api/v1/annual-reports/{report_id}/transition"): {"400", "409"},
    ("POST", "/api/v1/annual-reports/{report_id}/deadline"): {"400"},
    ("POST", "/api/v1/annual-reports/{report_id}/auto-populate"): {"400"},
    ("PATCH", "/api/v1/annual-reports/{report_id}/details"): {"400"},
    ("POST", "/api/v1/annual-reports/{report_id}/tax-calculation/save"): {"400"},
    ("POST", "/api/v1/annual-reports/{report_id}/income"): {"400"},
    ("PATCH", "/api/v1/annual-reports/{report_id}/income/{line_id}"): {"400"},
    ("DELETE", "/api/v1/annual-reports/{report_id}/income/{line_id}"): {"400"},
    ("POST", "/api/v1/annual-reports/{report_id}/expenses"): {"400"},
    ("PATCH", "/api/v1/annual-reports/{report_id}/expenses/{line_id}"): {"400"},
    ("DELETE", "/api/v1/annual-reports/{report_id}/expenses/{line_id}"): {"400"},
    ("POST", "/api/v1/annual-reports/{report_id}/annex/{schedule}"): {"400"},
    ("PATCH", "/api/v1/annual-reports/{report_id}/annex/{schedule}/{line_id}"): {"400"},
    ("DELETE", "/api/v1/annual-reports/{report_id}/annex/{schedule}/{line_id}"): {"400"},
    ("POST", "/api/v1/annual-reports/{report_id}/schedules"): {"400"},
    ("POST", "/api/v1/annual-reports/{report_id}/schedules/complete"): {"400"},
    # advance_payments
    ("POST", "/api/v1/clients/{client_record_id}/advance-payments"): {"400", "409"},
    ("POST", "/api/v1/clients/{client_record_id}/advance-payments/generate"): {"400", "409"},
    ("PATCH", "/api/v1/clients/{client_record_id}/advance-payments/{payment_id}"): {"400", "409"},
    # documents
    ("POST", "/api/v1/documents/upload"): {"400", "500"},
    ("PUT", "/api/v1/documents/client/{client_record_id}/{document_id}/replace"): {"400", "500"},
    ("DELETE", "/api/v1/documents/client/{client_record_id}/{document_id}"): {"400"},
    # tax_calendar
    ("POST", "/api/v1/settings/tax-calendar/bootstrap"): {"400", "409"},
    # charges (reference impl, pre-existing)
    ("POST", "/api/v1/charges"): {"400", "500"},
    ("POST", "/api/v1/charges/{charge_id}/cancel"): {"400", "409"},
    # clients
    ("POST", "/api/v1/clients"): {"400", "409"},
    ("POST", "/api/v1/clients/preview-impact"): {"400"},
    ("PATCH", "/api/v1/clients/{client_record_id}"): {"400", "409"},
    ("DELETE", "/api/v1/clients/{client_record_id}"): {"409"},
    ("POST", "/api/v1/clients/{client_record_id}/restore"): {"409"},
    # businesses
    ("POST", "/api/v1/clients/{client_record_id}/businesses"): {"400", "409"},
    ("PATCH", "/api/v1/clients/{client_record_id}/businesses/{business_id}"): {"400", "409"},
    ("DELETE", "/api/v1/clients/{client_record_id}/businesses/{business_id}"): {"409"},
    ("POST", "/api/v1/clients/{client_record_id}/businesses/{business_id}/restore"): {"409"},
    # tasks
    ("POST", "/api/v1/tasks"): {"400"},
    ("PATCH", "/api/v1/tasks/{task_id}"): {"400", "409"},
    ("POST", "/api/v1/tasks/{task_id}/complete"): {"409"},
    ("POST", "/api/v1/tasks/{task_id}/cancel"): {"409"},
    # invoices
    ("POST", "/api/v1/invoices"): {"400", "409"},
    # users
    ("POST", "/api/v1/users"): {"400", "409"},
    ("PATCH", "/api/v1/users/{user_id}"): {"400", "409"},
    ("POST", "/api/v1/users/{user_id}/activate"): {"409"},
    ("POST", "/api/v1/users/{user_id}/deactivate"): {"409"},
    ("POST", "/api/v1/users/{user_id}/reset-password"): {"400"},
    # communications
    ("POST", "/api/v1/clients/{client_record_id}/correspondence"): {"400"},
    ("PATCH", "/api/v1/clients/{client_record_id}/correspondence/{correspondence_id}"): {"400"},
    # notes
    ("POST", "/api/v1/clients/{client_record_id}/notes"): {"400"},
    ("PATCH", "/api/v1/clients/{client_record_id}/notes/{note_id}"): {"400"},
    ("POST", "/api/v1/clients/{client_record_id}/businesses/{business_id}/notes"): {"400"},
    ("PATCH", "/api/v1/clients/{client_record_id}/businesses/{business_id}/notes/{note_id}"): {"400"},
    # authority_contacts
    ("POST", "/api/v1/clients/{client_record_id}/authority-contacts"): {"400"},
    ("PATCH", "/api/v1/clients/{client_record_id}/authority-contacts/{contact_id}"): {"400"},
    # notifications
    ("POST", "/api/v1/notifications/preview"): {"400"},
    ("POST", "/api/v1/notifications/send"): {"400"},
    # reminders
    ("POST", "/api/v1/reminders/"): {"400"},
    ("POST", "/api/v1/reminders/{reminder_id}/cancel"): {"409"},
    # audit (the only non-write op with a body-driven 400)
    ("GET", "/api/v1/audit/{entity_type}/{entity_id}"): {"400"},
    # signature_requests
    ("POST", "/api/v1/signature-requests"): {"400"},
    ("POST", "/api/v1/clients/{client_record_id}/signature-requests/{request_id}/cancel"): {"409"},
    # auth
    ("POST", "/api/v1/auth/login"): {"400"},
    ("POST", "/api/v1/auth/reset-password"): {"400"},
}


def _documented_body_statuses() -> dict[tuple[str, str], set[str]]:
    spec = app.openapi()
    out: dict[tuple[str, str], set[str]] = {}
    for path, path_item in spec["paths"].items():
        for method, operation in path_item.items():
            if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            responses = operation.get("responses") or {}
            documented = {s for s in _BODY_STATUSES if s in responses}
            if documented:
                out[(method.upper(), path)] = documented
    return out


def test_every_expected_endpoint_documents_its_body_statuses():
    documented = _documented_body_statuses()
    missing = {
        key: expected - documented.get(key, set())
        for key, expected in _EXPECTED.items()
        if expected - documented.get(key, set())
    }
    assert not missing, f"endpoints missing documented body statuses: {missing}"


def test_no_unexpected_body_status_docs():
    documented = _documented_body_statuses()
    unexpected = {
        key: statuses - _EXPECTED.get(key, set())
        for key, statuses in documented.items()
        if statuses - _EXPECTED.get(key, set())
    }
    assert not unexpected, f"endpoints documenting unlisted body statuses: {unexpected}"
