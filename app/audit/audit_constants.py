"""
Entity-type and action constants for the generic audit log.

Use these constants in service code — never raw strings.

Actions are namespaced ``domain.action`` (e.g. ``client.created``,
``annual_report.status_changed``). Generic verbs (created/updated/deleted/
restored/status_changed) are *bare* building blocks here; the writer composes
the namespace from the entity_type via :func:`entity_action`. Domain-specific
verbs (charge.*, annual_report.* child actions) are defined pre-namespaced.
"""

# ---------------------------------------------------------------------------
# Entity types — canonical home for ENTITY_* (registry descriptors live in
# app/audit/audit_entity_registry.py and key off these values).
# ---------------------------------------------------------------------------
ENTITY_CLIENT = "client"
ENTITY_BUSINESS = "business"
ENTITY_LEGAL_ENTITY = "legal_entity"
ENTITY_PERSON = "person"
ENTITY_PERSON_LEGAL_ENTITY_LINK = "person_legal_entity_link"
ENTITY_AUTHORITY_CONTACT = "authority_contact"
ENTITY_NOTE = "note"
ENTITY_ADVANCE_PAYMENT = "advance_payment"
ENTITY_CHARGE = "charge"
ENTITY_INVOICE = "invoice"
ENTITY_VAT_WORK_ITEM = "vat_work_item"
ENTITY_VAT_INVOICE = "vat_invoice"
ENTITY_ANNUAL_REPORT = "annual_report"
ENTITY_BINDER = "binder"
ENTITY_BINDER_INTAKE = "binder_intake"
ENTITY_BINDER_HANDOVER = "binder_handover"
ENTITY_DOCUMENT = "document"
ENTITY_SIGNATURE_REQUEST = "signature_request"
ENTITY_TASK = "task"
ENTITY_CORRESPONDENCE = "correspondence"
ENTITY_NOTIFICATION = "notification"
ENTITY_REMINDER = "reminder"
ENTITY_TAX_CALENDAR = "tax_calendar"

INVALID_ENTITY_TYPE_ERROR = "סוג ישות לא נתמך להיסטוריית שינויים"
ENTITY_NOT_FOUND_ERROR = "הישות המבוקשת לא נמצאה"


def entity_action(entity_type: str, verb: str) -> str:
    """Namespace a bare verb under an entity type: ``client`` + ``created`` -> ``client.created``."""
    return f"{entity_type}.{verb}"


# ---------------------------------------------------------------------------
# Bare verbs — composed with an entity_type by the writer's record_* helpers.
# ---------------------------------------------------------------------------
ACTION_CREATED = "created"
ACTION_UPDATED = "updated"
ACTION_DELETED = "deleted"
ACTION_RESTORED = "restored"
ACTION_STATUS_CHANGED = "status_changed"

# Semantic action for a client legal entity-type change (pre-namespaced).
ACTION_ENTITY_TYPE_CHANGED = entity_action(ENTITY_CLIENT, "entity_type_changed")

# ---------------------------------------------------------------------------
# Charge-specific status transitions (pre-namespaced).
# ---------------------------------------------------------------------------
ACTION_CHARGE_ISSUED = entity_action(ENTITY_CHARGE, "issued")
ACTION_CHARGE_PAID = entity_action(ENTITY_CHARGE, "paid")
ACTION_CHARGE_CANCELED = entity_action(ENTITY_CHARGE, "canceled")

# ---------------------------------------------------------------------------
# Annual-report actions (pre-namespaced; child actions keep rich semantics §7a).
# ---------------------------------------------------------------------------
ACTION_ANNUAL_REPORT_DETAIL_UPDATED = entity_action(ENTITY_ANNUAL_REPORT, "updated")
ACTION_ANNUAL_REPORT_DEADLINE_UPDATED = entity_action(ENTITY_ANNUAL_REPORT, "deadline_updated")
ACTION_ANNEX_LINE_ADDED = entity_action(ENTITY_ANNUAL_REPORT, "annex_line_added")
ACTION_ANNEX_LINE_UPDATED = entity_action(ENTITY_ANNUAL_REPORT, "annex_line_updated")
ACTION_ANNEX_LINE_DELETED = entity_action(ENTITY_ANNUAL_REPORT, "annex_line_deleted")

ACTION_INCOME_ADDED = entity_action(ENTITY_ANNUAL_REPORT, "income_line_added")
ACTION_INCOME_UPDATED = entity_action(ENTITY_ANNUAL_REPORT, "income_line_updated")
ACTION_INCOME_DELETED = entity_action(ENTITY_ANNUAL_REPORT, "income_line_deleted")
ACTION_EXPENSE_ADDED = entity_action(ENTITY_ANNUAL_REPORT, "expense_line_added")
ACTION_EXPENSE_UPDATED = entity_action(ENTITY_ANNUAL_REPORT, "expense_line_updated")
ACTION_EXPENSE_DELETED = entity_action(ENTITY_ANNUAL_REPORT, "expense_line_deleted")

# ---------------------------------------------------------------------------
# VAT actions (pre-namespaced). Work-item lifecycle events anchor on the
# vat_work_item entity; invoice events anchor on the vat_invoice entity (the
# owning work item is carried in metadata_json.vat_work_item_id).
# ---------------------------------------------------------------------------
ACTION_VAT_WORK_ITEM_CREATED = entity_action(ENTITY_VAT_WORK_ITEM, ACTION_CREATED)
ACTION_VAT_WORK_ITEM_STATUS_CHANGED = entity_action(ENTITY_VAT_WORK_ITEM, ACTION_STATUS_CHANGED)
ACTION_VAT_WORK_ITEM_FILED = entity_action(ENTITY_VAT_WORK_ITEM, "filed")
ACTION_VAT_WORK_ITEM_AMOUNT_OVERRIDDEN = entity_action(ENTITY_VAT_WORK_ITEM, "amount_overridden")
ACTION_VAT_WORK_ITEM_UPDATED = entity_action(ENTITY_VAT_WORK_ITEM, ACTION_UPDATED)
ACTION_VAT_WORK_ITEM_DELETED = entity_action(ENTITY_VAT_WORK_ITEM, ACTION_DELETED)

ACTION_VAT_INVOICE_CREATED = entity_action(ENTITY_VAT_INVOICE, ACTION_CREATED)
ACTION_VAT_INVOICE_UPDATED = entity_action(ENTITY_VAT_INVOICE, ACTION_UPDATED)
ACTION_VAT_INVOICE_AMOUNT_CHANGED = entity_action(ENTITY_VAT_INVOICE, "amount_changed")
ACTION_VAT_INVOICE_DELETED = entity_action(ENTITY_VAT_INVOICE, ACTION_DELETED)

# ---------------------------------------------------------------------------
# Binder lifecycle actions (pre-namespaced). Each rich semantic verb replaces a
# BinderLifecycleLog field-change row; the changed status is carried in
# old_value/new_value and the client context in metadata_json.client_record_id.
# binder.created/handed_over/material_received are also surfaced by live timeline
# builders, so timeline reads them from those builders, not from these rows.
# ---------------------------------------------------------------------------
ACTION_BINDER_CREATED = entity_action(ENTITY_BINDER, ACTION_CREATED)
ACTION_BINDER_MATERIAL_RECEIVED = entity_action(ENTITY_BINDER, "material_received")
ACTION_BINDER_MARKED_FULL = entity_action(ENTITY_BINDER, "marked_full")
ACTION_BINDER_REOPENED = entity_action(ENTITY_BINDER, "reopened")
ACTION_BINDER_MARKED_READY_FOR_HANDOVER = entity_action(ENTITY_BINDER, "marked_ready_for_handover")
ACTION_BINDER_REVERTED_READY = entity_action(ENTITY_BINDER, "reverted_ready")
ACTION_BINDER_HANDED_OVER = entity_action(ENTITY_BINDER, "handed_over")

# ---------------------------------------------------------------------------
# Binder-intake edit actions (pre-namespaced). A single PATCH may touch the
# intake row and its materials; each changed field is one binder_intake.updated
# row with the field identity in metadata_json (§10b).
# ---------------------------------------------------------------------------
ACTION_BINDER_INTAKE_UPDATED = entity_action(ENTITY_BINDER_INTAKE, ACTION_UPDATED)
