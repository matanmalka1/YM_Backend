"""Fail-closed write-time validation for EntityAuditLog payloads.

Enforced on EVERY write inside the domain transaction (an invalid payload raises
and rolls the domain mutation back — §16/§17):

1. **Actor matrix (§5a)** — actor_type/performed_by/actor_display_name combo.
2. **Namespace match** — the action's `<entity_type>.` prefix must equal the row's
   entity_type (a `client` row may not carry a `signature_request.*` action).
3. **Per-(entity_type, action) policy (§16)** — every action has an explicit
   policy: a positive top-level field allowlist for `old_value`/`new_value`
   (so document content / unexpected fields reject — they are in no allowlist),
   plus required + allowed `metadata_json` keys. `metadata_json` must be an
   object (a list/scalar is rejected, never silently skipped).
4. **Recursive forbidden-key denylist + raw-bytes block** — defense-in-depth for
   nested values (e.g. inside an annex `data` blob).
5. **Compact-UTF-8-JSON size caps** — old/new 32 KiB each, metadata 16 KiB.

Violations are integrity invariants, not client input errors, so they raise
``AppError`` with HTTP 500 — surfacing the defect loudly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, NoReturn

from app.audit.audit_constants import (
    ACTION_ADVANCE_PAYMENT_CREATED,
    ACTION_ADVANCE_PAYMENT_DELETED,
    ACTION_ADVANCE_PAYMENT_TURNOVER_REFRESHED,
    ACTION_ADVANCE_PAYMENT_UPDATED,
    ACTION_ANNEX_LINE_ADDED,
    ACTION_ANNEX_LINE_DELETED,
    ACTION_ANNEX_LINE_UPDATED,
    ACTION_ANNUAL_REPORT_DEADLINE_UPDATED,
    ACTION_ANNUAL_REPORT_DETAIL_UPDATED,
    ACTION_AUTHORITY_CONTACT_CREATED,
    ACTION_AUTHORITY_CONTACT_DELETED,
    ACTION_AUTHORITY_CONTACT_UPDATED,
    ACTION_BINDER_CREATED,
    ACTION_BINDER_HANDED_OVER,
    ACTION_BINDER_INTAKE_UPDATED,
    ACTION_BINDER_MARKED_FULL,
    ACTION_BINDER_MARKED_READY_FOR_HANDOVER,
    ACTION_BINDER_MATERIAL_RECEIVED,
    ACTION_BINDER_REOPENED,
    ACTION_BINDER_REVERTED_READY,
    ACTION_CHARGE_CANCELED,
    ACTION_CHARGE_ISSUED,
    ACTION_CHARGE_PAID,
    ACTION_CORRESPONDENCE_CREATED,
    ACTION_CORRESPONDENCE_DELETED,
    ACTION_CORRESPONDENCE_UPDATED,
    ACTION_CREATED,
    ACTION_DELETED,
    ACTION_DOCUMENT_DELETED,
    ACTION_DOCUMENT_REPLACED,
    ACTION_DOCUMENT_UPDATED,
    ACTION_DOCUMENT_UPLOADED,
    ACTION_ENTITY_TYPE_CHANGED,
    ACTION_EXPENSE_ADDED,
    ACTION_EXPENSE_DELETED,
    ACTION_EXPENSE_UPDATED,
    ACTION_INCOME_ADDED,
    ACTION_INCOME_DELETED,
    ACTION_INCOME_UPDATED,
    ACTION_INVOICE_CREATED,
    ACTION_LEGAL_ENTITY_CREATED,
    ACTION_LEGAL_ENTITY_UPDATED,
    ACTION_NOTE_CREATED,
    ACTION_NOTE_DELETED,
    ACTION_NOTE_UPDATED,
    ACTION_NOTIFICATION_SENT,
    ACTION_PERSON_CREATED,
    ACTION_PERSON_LEGAL_ENTITY_LINK_CREATED,
    ACTION_PERSON_LEGAL_ENTITY_LINK_DELETED,
    ACTION_PERSON_UPDATED,
    ACTION_REMINDER_CANCELED,
    ACTION_REMINDER_CREATED,
    ACTION_REMINDER_FAILED,
    ACTION_REMINDER_FIRED,
    ACTION_RESTORED,
    ACTION_SIGNATURE_REQUEST_ANNUAL_REPORT_SIGNED,
    ACTION_SIGNATURE_REQUEST_CANCELED,
    ACTION_SIGNATURE_REQUEST_CREATED,
    ACTION_SIGNATURE_REQUEST_DECLINED,
    ACTION_SIGNATURE_REQUEST_EXPIRED,
    ACTION_SIGNATURE_REQUEST_SENT,
    ACTION_SIGNATURE_REQUEST_SIGNED,
    ACTION_SIGNATURE_REQUEST_VIEWED,
    ACTION_STATUS_CHANGED,
    ACTION_TASK_ASSIGNED,
    ACTION_TASK_CANCELED,
    ACTION_TASK_COMPLETED,
    ACTION_TASK_CREATED,
    ACTION_TASK_DELETED,
    ACTION_TASK_UPDATED,
    ACTION_TAX_CALENDAR_GENERATED,
    ACTION_UPDATED,
    ACTION_VAT_INVOICE_AMOUNT_CHANGED,
    ACTION_VAT_INVOICE_CREATED,
    ACTION_VAT_INVOICE_DELETED,
    ACTION_VAT_INVOICE_UPDATED,
    ACTION_VAT_WORK_ITEM_AMOUNT_OVERRIDDEN,
    ACTION_VAT_WORK_ITEM_CREATED,
    ACTION_VAT_WORK_ITEM_DELETED,
    ACTION_VAT_WORK_ITEM_FILED,
    ACTION_VAT_WORK_ITEM_STATUS_CHANGED,
    ACTION_VAT_WORK_ITEM_UPDATED,
    ENTITY_ANNUAL_REPORT,
    ENTITY_BUSINESS,
    ENTITY_CHARGE,
    ENTITY_CLIENT,
    entity_action,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError

VALID_ACTOR_TYPES = ("user", "system", "external_signer")

OLD_NEW_VALUE_MAX_BYTES = 32 * 1024
METADATA_MAX_BYTES = 16 * 1024

# Recursive denylist (defense-in-depth; the positive value allowlist is the
# primary control). Catches password_hash, *token*, *secret*, signing_token,
# raw document content / file bytes anywhere in the payload.
_FORBIDDEN_KEY_SUBSTRINGS = (
    "password",
    "token",
    "secret",
    "private_key",
    "api_key",
    "signing",
    "document_content",
    "file_content",
    "raw_content",
    "content_snapshot",
    "file_bytes",
)

# Client context columns shared by client-scoped metadata.
_AR_META = frozenset(
    {"client_record_id", "tax_year", "section", "line_id", "schedule_id", "line_number"}
)
_CHARGE_META = frozenset({"client_record_id", "business_id", "annual_report_id", "invoice_id"})
_BUSINESS_META = frozenset({"client_record_id", "business_id"})
_SIGNATURE_BASE_META = frozenset(
    {
        "client_record_id",
        "signer_name",
        "signer_email",
        "business_id",
        "annual_report_id",
        "document_id",
    }
)
_SIGNATURE_CLIENT_META = frozenset({"ip_address", "user_agent"})
_SIGNATURE_SIGNED_META = frozenset({"content_hash", "content_hash_missing", "signed_document_key"})

# Top-level value-field allowlists (bounded by the request/snapshot shapes).
_CLIENT_UPDATE_FIELDS = frozenset(
    {
        "full_name",
        "status",
        "entity_type",
        "phone",
        "email",
        "address_street",
        "address_building_number",
        "address_apartment",
        "address_city",
        "address_zip_code",
        "vat_reporting_frequency",
        "advance_payment_frequency",
        "vat_exempt_ceiling",
        "advance_rate",
        "advance_rate_updated_at",
        "annual_revenue",
        "accountant_id",
    }
)
# vat-import mutations annotate the line snapshot with provenance keys.
_VAT_IMPORT_EXTRA = frozenset(
    {"mutation_source", "mutation_reason", "source", "source_total", "source_vat_categories"}
)
_INCOME_FIELDS = frozenset({"line_id", "source_type", "amount", "description"}) | _VAT_IMPORT_EXTRA
_EXPENSE_FIELDS = (
    frozenset(
        {
            "line_id",
            "category",
            "amount",
            "recognition_rate",
            "external_document_reference",
            "supporting_document_id",
            "description",
        }
    )
    | _VAT_IMPORT_EXTRA
)
_ANNEX_FIELDS = frozenset({"schedule", "line_id", "line_number", "data", "notes"})
_STATUS_ONLY = frozenset({"status"})

# VAT metadata: client_record_id is the indexed client context (§8); period/
# tax_year give the reporting period; invoice events additionally carry the
# owning work item + invoice identity.
_VAT_WORK_ITEM_META = frozenset({"client_record_id", "period", "tax_year", "source"})
_VAT_INVOICE_META = frozenset(
    {
        "client_record_id",
        "vat_work_item_id",
        "invoice_number",
        "period",
        "tax_year",
        "business_id",
        "source",
    }
)
# Invoice snapshot keys captured in old_value/new_value.
_VAT_INVOICE_FIELDS = frozenset({"invoice_id", "type", "number", "vat_amount"})

# Binder lifecycle: old_value/new_value carry the changed status field; metadata
# carries the indexed client context plus binder identity (§8).
_BINDER_LIFECYCLE_FIELDS = frozenset({"location_status", "capacity_status"})
_BINDER_META = frozenset({"client_record_id", "binder_id", "binder_number"})
# Binder-intake edit: each changed field is one row; the value is wrapped as
# {"value": ...}; metadata carries client context + binder/intake/field identity (§8/§10b).
_BINDER_INTAKE_META = frozenset({"client_record_id", "binder_id", "intake_id", "field_name"})

_LEGAL_ENTITY_META = frozenset({"client_record_id", "legal_entity_id"})
_LEGAL_ENTITY_FIELDS = frozenset(
    {
        "id_number",
        "id_number_type",
        "official_name",
        "entity_type",
        "vat_reporting_frequency",
        "advance_payment_frequency",
        "vat_exempt_ceiling",
        "advance_rate",
        "advance_rate_updated_at",
        "annual_revenue",
    }
)
_PERSON_META = frozenset({"client_record_id", "legal_entity_id", "person_id"})
_PERSON_FIELDS = frozenset(
    {
        "full_name",
        "id_number",
        "id_number_type",
        "phone",
        "email",
        "address_street",
        "address_building_number",
        "address_apartment",
        "address_city",
        "address_zip_code",
    }
)
_PERSON_LINK_META = frozenset({"client_record_id", "legal_entity_id", "person_id", "link_id"})
_PERSON_LINK_FIELDS = frozenset({"person_id", "legal_entity_id", "role"})
_AUTHORITY_CONTACT_META = frozenset({"client_record_id", "contact_id"})
_AUTHORITY_CONTACT_FIELDS = frozenset({"contact_type", "name", "office", "phone", "email", "notes"})
_ADVANCE_PAYMENT_META = frozenset(
    {
        "client_record_id",
        "period",
        "tax_year",
        "annual_report_id",
        "source",
        "vat_work_item_ids",
    }
)
_ADVANCE_PAYMENT_FIELDS = frozenset(
    {
        "period",
        "period_months_count",
        "due_date",
        "expected_amount",
        "paid_amount",
        "payment_method",
        "payment_reference",
        "annual_report_id",
        "notes",
        "advance_rate",
        "turnover_amount",
        "turnover_source",
        "turnover_snapshot_at",
        "calculated_amount",
        "override_amount",
        "status",
        "paid_at",
    }
)
_DOCUMENT_META = frozenset(
    {
        "client_record_id",
        "business_id",
        "annual_report_id",
        "document_type",
        "tax_year",
        "version",
        "mime_type",
        "file_size_bytes",
    }
)
_DOCUMENT_FIELDS = frozenset(
    {
        "document_type",
        "original_filename",
        "tax_year",
        "status",
        "version",
        "file_size_bytes",
        "mime_type",
        "is_deleted",
    }
)
_INVOICE_META = frozenset({"client_record_id", "business_id", "annual_report_id", "invoice_id"})
_INVOICE_FIELDS = frozenset(
    {"charge_id", "provider", "external_invoice_id", "document_url", "issued_at"}
)
_NOTE_META = frozenset({"client_record_id", "note_id", "entity_type", "entity_id"})
_NOTE_FIELDS = frozenset({"body", "is_pinned"})
_TASK_META = frozenset(
    {
        "client_record_id",
        "source_domain",
        "source_id",
        "assigned_to_user_id",
        "assigned_role",
    }
)
_TASK_FIELDS = frozenset(
    {
        "title",
        "description",
        "status",
        "priority",
        "due_date",
        "assigned_to_user_id",
        "assigned_role",
        "source_domain",
        "source_id",
        "client_record_id",
        "action_key",
        "action_payload",
    }
)
_CORRESPONDENCE_META = frozenset({"client_record_id", "business_id", "contact_id"})
_CORRESPONDENCE_FIELDS = frozenset(
    {"correspondence_type", "subject", "occurred_at", "business_id", "contact_id", "notes"}
)
_NOTIFICATION_META = frozenset(
    {
        "client_record_id",
        "business_id",
        "trigger",
        "channel",
        "entity_type",
        "entity_id",
        "binder_id",
        "annual_report_id",
        "signature_request_id",
    }
)
_NOTIFICATION_FIELDS = frozenset({"status", "recipient", "subject_snapshot"})
_REMINDER_META = frozenset(
    {"client_record_id", "source_domain", "source_id", "target_task_id", "action_type"}
)
_REMINDER_FIELDS = frozenset(
    {
        "status",
        "fire_at",
        "action_type",
        "source_domain",
        "source_id",
        "target_task_id",
        "notification_template_key",
        "failure_reason",
    }
)
_TAX_CALENDAR_META = frozenset({"start_year", "end_year", "entries_created", "entries_skipped"})
_TAX_CALENDAR_FIELDS = frozenset({"start_year", "end_year", "entries_created", "entries_skipped"})


@dataclass(frozen=True)
class ActionPolicy:
    value_fields: frozenset[str] = frozenset()
    metadata_required: frozenset[str] = frozenset()
    metadata_allowed: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        # required must be a subset of allowed
        object.__setattr__(self, "metadata_allowed", self.metadata_allowed | self.metadata_required)


def _ar(action_verb: str) -> str:
    return entity_action(ENTITY_ANNUAL_REPORT, action_verb)


# Per-(entity_type, action) policy. Keyed by the full namespaced action string.
ACTION_POLICIES: dict[str, ActionPolicy] = {
    # client
    entity_action(ENTITY_CLIENT, ACTION_CREATED): ActionPolicy(
        value_fields=frozenset({"full_name", "id_number", "entity_type", "office_client_number"}),
        metadata_required=frozenset({"client_record_id"}),
    ),
    entity_action(ENTITY_CLIENT, ACTION_UPDATED): ActionPolicy(
        value_fields=_CLIENT_UPDATE_FIELDS,
        metadata_required=frozenset({"client_record_id"}),
    ),
    ACTION_ENTITY_TYPE_CHANGED: ActionPolicy(
        value_fields=frozenset({"entity_type"}),
        metadata_required=frozenset({"client_record_id"}),
    ),
    entity_action(ENTITY_CLIENT, ACTION_DELETED): ActionPolicy(
        metadata_required=frozenset({"client_record_id"})
    ),
    entity_action(ENTITY_CLIENT, ACTION_RESTORED): ActionPolicy(
        metadata_required=frozenset({"client_record_id"})
    ),
    # business
    entity_action(ENTITY_BUSINESS, ACTION_CREATED): ActionPolicy(
        value_fields=frozenset({"client_record_id", "business_name", "opened_at"}),
        metadata_required=frozenset({"client_record_id", "business_id"}),
        metadata_allowed=_BUSINESS_META,
    ),
    entity_action(ENTITY_BUSINESS, ACTION_UPDATED): ActionPolicy(
        value_fields=frozenset({"business_name", "status", "closed_at"}),
        metadata_required=frozenset({"client_record_id", "business_id"}),
        metadata_allowed=_BUSINESS_META,
    ),
    entity_action(ENTITY_BUSINESS, ACTION_DELETED): ActionPolicy(
        metadata_required=frozenset({"client_record_id", "business_id"}),
        metadata_allowed=_BUSINESS_META,
    ),
    entity_action(ENTITY_BUSINESS, ACTION_RESTORED): ActionPolicy(
        metadata_required=frozenset({"client_record_id", "business_id"}),
        metadata_allowed=_BUSINESS_META,
    ),
    # legal_entity/person/link (created through client/business graph writes).
    ACTION_LEGAL_ENTITY_CREATED: ActionPolicy(
        value_fields=_LEGAL_ENTITY_FIELDS,
        metadata_required=frozenset({"client_record_id", "legal_entity_id"}),
        metadata_allowed=_LEGAL_ENTITY_META,
    ),
    ACTION_LEGAL_ENTITY_UPDATED: ActionPolicy(
        value_fields=_LEGAL_ENTITY_FIELDS,
        metadata_required=frozenset({"client_record_id", "legal_entity_id"}),
        metadata_allowed=_LEGAL_ENTITY_META,
    ),
    ACTION_PERSON_CREATED: ActionPolicy(
        value_fields=_PERSON_FIELDS,
        metadata_required=frozenset({"client_record_id", "legal_entity_id", "person_id"}),
        metadata_allowed=_PERSON_META,
    ),
    ACTION_PERSON_UPDATED: ActionPolicy(
        value_fields=_PERSON_FIELDS,
        metadata_required=frozenset({"client_record_id", "legal_entity_id", "person_id"}),
        metadata_allowed=_PERSON_META,
    ),
    ACTION_PERSON_LEGAL_ENTITY_LINK_CREATED: ActionPolicy(
        value_fields=_PERSON_LINK_FIELDS,
        metadata_required=frozenset(
            {"client_record_id", "legal_entity_id", "person_id", "link_id"}
        ),
        metadata_allowed=_PERSON_LINK_META,
    ),
    ACTION_PERSON_LEGAL_ENTITY_LINK_DELETED: ActionPolicy(
        value_fields=_PERSON_LINK_FIELDS,
        metadata_required=frozenset(
            {"client_record_id", "legal_entity_id", "person_id", "link_id"}
        ),
        metadata_allowed=_PERSON_LINK_META,
    ),
    # authority_contact
    ACTION_AUTHORITY_CONTACT_CREATED: ActionPolicy(
        value_fields=_AUTHORITY_CONTACT_FIELDS,
        metadata_required=frozenset({"client_record_id", "contact_id"}),
        metadata_allowed=_AUTHORITY_CONTACT_META,
    ),
    ACTION_AUTHORITY_CONTACT_UPDATED: ActionPolicy(
        value_fields=_AUTHORITY_CONTACT_FIELDS,
        metadata_required=frozenset({"client_record_id", "contact_id"}),
        metadata_allowed=_AUTHORITY_CONTACT_META,
    ),
    ACTION_AUTHORITY_CONTACT_DELETED: ActionPolicy(
        value_fields=_AUTHORITY_CONTACT_FIELDS,
        metadata_required=frozenset({"client_record_id", "contact_id"}),
        metadata_allowed=_AUTHORITY_CONTACT_META,
    ),
    # advance_payment
    ACTION_ADVANCE_PAYMENT_CREATED: ActionPolicy(
        value_fields=_ADVANCE_PAYMENT_FIELDS,
        metadata_required=frozenset({"client_record_id", "period", "tax_year"}),
        metadata_allowed=_ADVANCE_PAYMENT_META,
    ),
    ACTION_ADVANCE_PAYMENT_UPDATED: ActionPolicy(
        value_fields=_ADVANCE_PAYMENT_FIELDS,
        metadata_required=frozenset({"client_record_id", "period", "tax_year"}),
        metadata_allowed=_ADVANCE_PAYMENT_META,
    ),
    ACTION_ADVANCE_PAYMENT_DELETED: ActionPolicy(
        value_fields=_ADVANCE_PAYMENT_FIELDS,
        metadata_required=frozenset({"client_record_id", "period", "tax_year", "reason"}),
        metadata_allowed=_ADVANCE_PAYMENT_META | frozenset({"reason"}),
    ),
    ACTION_ADVANCE_PAYMENT_TURNOVER_REFRESHED: ActionPolicy(
        value_fields=_ADVANCE_PAYMENT_FIELDS,
        metadata_required=frozenset(
            {"client_record_id", "period", "tax_year", "source", "vat_work_item_ids"}
        ),
        metadata_allowed=_ADVANCE_PAYMENT_META,
    ),
    # charge
    entity_action(ENTITY_CHARGE, ACTION_CREATED): ActionPolicy(
        value_fields=frozenset({"amount", "charge_type"}),
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_CHARGE_META,
    ),
    entity_action(ENTITY_CHARGE, ACTION_UPDATED): ActionPolicy(
        value_fields=frozenset(
            {"amount", "charge_type", "period", "months_covered", "description", "business_id"}
        ),
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_CHARGE_META,
    ),
    ACTION_CHARGE_ISSUED: ActionPolicy(
        value_fields=_STATUS_ONLY,
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_CHARGE_META,
    ),
    ACTION_CHARGE_PAID: ActionPolicy(
        value_fields=_STATUS_ONLY,
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_CHARGE_META,
    ),
    ACTION_CHARGE_CANCELED: ActionPolicy(
        value_fields=_STATUS_ONLY,
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_CHARGE_META,
    ),
    entity_action(ENTITY_CHARGE, ACTION_DELETED): ActionPolicy(
        metadata_required=frozenset({"client_record_id"}), metadata_allowed=_CHARGE_META
    ),
    # invoice
    ACTION_INVOICE_CREATED: ActionPolicy(
        value_fields=_INVOICE_FIELDS,
        metadata_required=frozenset({"client_record_id", "invoice_id"}),
        metadata_allowed=_INVOICE_META,
    ),
    # annual_report
    _ar(ACTION_CREATED): ActionPolicy(
        value_fields=frozenset({"tax_year", "client_type", "client_record_id", "form_type"}),
        metadata_required=frozenset({"client_record_id", "tax_year"}),
        metadata_allowed=_AR_META,
    ),
    _ar(ACTION_STATUS_CHANGED): ActionPolicy(
        value_fields=_STATUS_ONLY,
        metadata_required=frozenset({"client_record_id", "tax_year"}),
        metadata_allowed=_AR_META,
    ),
    _ar(ACTION_DELETED): ActionPolicy(
        metadata_required=frozenset({"client_record_id", "tax_year"}),
        metadata_allowed=_AR_META,
    ),
    ACTION_ANNUAL_REPORT_DETAIL_UPDATED: ActionPolicy(
        value_fields=frozenset(
            {
                "pension_contribution",
                "donation_amount",
                "other_credits",
                "client_approved_at",
                "internal_notes",
                "amendment_reason",
            }
        ),
        metadata_required=frozenset({"client_record_id", "tax_year"}),
        metadata_allowed=_AR_META,
    ),
    ACTION_ANNUAL_REPORT_DEADLINE_UPDATED: ActionPolicy(
        value_fields=frozenset({"deadline_type", "filing_deadline", "custom_deadline_note"}),
        metadata_required=frozenset({"client_record_id", "tax_year"}),
        metadata_allowed=_AR_META,
    ),
    ACTION_INCOME_ADDED: ActionPolicy(
        value_fields=_INCOME_FIELDS,
        metadata_required=frozenset({"client_record_id", "tax_year", "section", "line_id"}),
        metadata_allowed=_AR_META,
    ),
    ACTION_INCOME_UPDATED: ActionPolicy(
        value_fields=_INCOME_FIELDS,
        metadata_required=frozenset({"client_record_id", "tax_year", "section", "line_id"}),
        metadata_allowed=_AR_META,
    ),
    ACTION_INCOME_DELETED: ActionPolicy(
        value_fields=_INCOME_FIELDS,
        metadata_required=frozenset({"client_record_id", "tax_year", "section", "line_id"}),
        metadata_allowed=_AR_META,
    ),
    ACTION_EXPENSE_ADDED: ActionPolicy(
        value_fields=_EXPENSE_FIELDS,
        metadata_required=frozenset({"client_record_id", "tax_year", "section", "line_id"}),
        metadata_allowed=_AR_META,
    ),
    ACTION_EXPENSE_UPDATED: ActionPolicy(
        value_fields=_EXPENSE_FIELDS,
        metadata_required=frozenset({"client_record_id", "tax_year", "section", "line_id"}),
        metadata_allowed=_AR_META,
    ),
    ACTION_EXPENSE_DELETED: ActionPolicy(
        value_fields=_EXPENSE_FIELDS,
        metadata_required=frozenset({"client_record_id", "tax_year", "section", "line_id"}),
        metadata_allowed=_AR_META,
    ),
    ACTION_ANNEX_LINE_ADDED: ActionPolicy(
        value_fields=_ANNEX_FIELDS,
        metadata_required=frozenset(
            {"client_record_id", "tax_year", "line_id", "schedule_id", "line_number"}
        ),
        metadata_allowed=_AR_META,
    ),
    ACTION_ANNEX_LINE_UPDATED: ActionPolicy(
        value_fields=_ANNEX_FIELDS,
        metadata_required=frozenset(
            {"client_record_id", "tax_year", "line_id", "schedule_id", "line_number"}
        ),
        metadata_allowed=_AR_META,
    ),
    ACTION_ANNEX_LINE_DELETED: ActionPolicy(
        value_fields=_ANNEX_FIELDS,
        metadata_required=frozenset(
            {"client_record_id", "tax_year", "line_id", "schedule_id", "line_number"}
        ),
        metadata_allowed=_AR_META,
    ),
    # vat_work_item (lifecycle on the work item itself).
    ACTION_VAT_WORK_ITEM_CREATED: ActionPolicy(
        value_fields=frozenset({"status", "period"}),
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_VAT_WORK_ITEM_META,
    ),
    ACTION_VAT_WORK_ITEM_STATUS_CHANGED: ActionPolicy(
        value_fields=_STATUS_ONLY,
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_VAT_WORK_ITEM_META,
    ),
    ACTION_VAT_WORK_ITEM_FILED: ActionPolicy(
        value_fields=frozenset({"final_vat_amount", "submission_method", "is_overridden"}),
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_VAT_WORK_ITEM_META,
    ),
    ACTION_VAT_WORK_ITEM_AMOUNT_OVERRIDDEN: ActionPolicy(
        value_fields=frozenset({"final_vat_amount"}),
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_VAT_WORK_ITEM_META,
    ),
    ACTION_VAT_WORK_ITEM_UPDATED: ActionPolicy(
        value_fields=frozenset({"assigned_to", "pending_materials_note"}),
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_VAT_WORK_ITEM_META,
    ),
    ACTION_VAT_WORK_ITEM_DELETED: ActionPolicy(
        value_fields=_STATUS_ONLY,
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_VAT_WORK_ITEM_META,
    ),
    # vat_invoice (line-item events; owning work item carried in metadata).
    ACTION_VAT_INVOICE_CREATED: ActionPolicy(
        value_fields=_VAT_INVOICE_FIELDS,
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_VAT_INVOICE_META,
    ),
    ACTION_VAT_INVOICE_UPDATED: ActionPolicy(
        value_fields=_VAT_INVOICE_FIELDS,
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_VAT_INVOICE_META,
    ),
    ACTION_VAT_INVOICE_AMOUNT_CHANGED: ActionPolicy(
        value_fields=_VAT_INVOICE_FIELDS,
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_VAT_INVOICE_META,
    ),
    ACTION_VAT_INVOICE_DELETED: ActionPolicy(
        value_fields=_VAT_INVOICE_FIELDS,
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_VAT_INVOICE_META,
    ),
    # binder lifecycle (rich semantic verbs replacing BinderLifecycleLog rows §10b).
    ACTION_BINDER_CREATED: ActionPolicy(
        value_fields=_BINDER_LIFECYCLE_FIELDS,
        metadata_required=frozenset({"client_record_id", "binder_id"}),
        metadata_allowed=_BINDER_META,
    ),
    ACTION_BINDER_MATERIAL_RECEIVED: ActionPolicy(
        value_fields=_BINDER_LIFECYCLE_FIELDS,
        metadata_required=frozenset({"client_record_id", "binder_id"}),
        metadata_allowed=_BINDER_META,
    ),
    ACTION_BINDER_MARKED_FULL: ActionPolicy(
        value_fields=_BINDER_LIFECYCLE_FIELDS,
        metadata_required=frozenset({"client_record_id", "binder_id"}),
        metadata_allowed=_BINDER_META,
    ),
    ACTION_BINDER_REOPENED: ActionPolicy(
        value_fields=_BINDER_LIFECYCLE_FIELDS,
        metadata_required=frozenset({"client_record_id", "binder_id"}),
        metadata_allowed=_BINDER_META,
    ),
    ACTION_BINDER_MARKED_READY_FOR_HANDOVER: ActionPolicy(
        value_fields=_BINDER_LIFECYCLE_FIELDS,
        metadata_required=frozenset({"client_record_id", "binder_id"}),
        metadata_allowed=_BINDER_META,
    ),
    ACTION_BINDER_REVERTED_READY: ActionPolicy(
        value_fields=_BINDER_LIFECYCLE_FIELDS,
        metadata_required=frozenset({"client_record_id", "binder_id"}),
        metadata_allowed=_BINDER_META,
    ),
    ACTION_BINDER_HANDED_OVER: ActionPolicy(
        value_fields=_BINDER_LIFECYCLE_FIELDS,
        metadata_required=frozenset({"client_record_id", "binder_id"}),
        metadata_allowed=_BINDER_META,
    ),
    # binder_intake edit (field-level; value wrapped as {"value": ...}) (§10b).
    ACTION_BINDER_INTAKE_UPDATED: ActionPolicy(
        value_fields=frozenset({"value"}),
        metadata_required=frozenset({"client_record_id", "binder_id", "intake_id", "field_name"}),
        metadata_allowed=_BINDER_INTAKE_META,
    ),
    # document
    ACTION_DOCUMENT_UPLOADED: ActionPolicy(
        value_fields=_DOCUMENT_FIELDS,
        metadata_required=frozenset({"client_record_id", "document_type", "version"}),
        metadata_allowed=_DOCUMENT_META,
    ),
    ACTION_DOCUMENT_UPDATED: ActionPolicy(
        value_fields=_DOCUMENT_FIELDS,
        metadata_required=frozenset({"client_record_id", "document_type", "version"}),
        metadata_allowed=_DOCUMENT_META,
    ),
    ACTION_DOCUMENT_REPLACED: ActionPolicy(
        value_fields=_DOCUMENT_FIELDS,
        metadata_required=frozenset({"client_record_id", "document_type", "version"}),
        metadata_allowed=_DOCUMENT_META,
    ),
    ACTION_DOCUMENT_DELETED: ActionPolicy(
        value_fields=_DOCUMENT_FIELDS,
        metadata_required=frozenset({"client_record_id", "document_type", "version"}),
        metadata_allowed=_DOCUMENT_META,
    ),
    # signature_request (evidence; per-action forensic metadata §8a).
    ACTION_SIGNATURE_REQUEST_CREATED: ActionPolicy(
        metadata_required=frozenset({"client_record_id", "signer_name"}),
        metadata_allowed=_SIGNATURE_BASE_META,
    ),
    ACTION_SIGNATURE_REQUEST_SENT: ActionPolicy(
        metadata_required=frozenset({"client_record_id", "signer_name"}),
        metadata_allowed=_SIGNATURE_BASE_META,
    ),
    ACTION_SIGNATURE_REQUEST_ANNUAL_REPORT_SIGNED: ActionPolicy(
        metadata_required=frozenset({"client_record_id", "signer_name"}),
        metadata_allowed=_SIGNATURE_BASE_META,
    ),
    ACTION_SIGNATURE_REQUEST_VIEWED: ActionPolicy(
        metadata_required=frozenset({"client_record_id", "signer_name"}),
        metadata_allowed=_SIGNATURE_BASE_META | _SIGNATURE_CLIENT_META,
    ),
    ACTION_SIGNATURE_REQUEST_DECLINED: ActionPolicy(
        metadata_required=frozenset({"client_record_id", "signer_name"}),
        metadata_allowed=_SIGNATURE_BASE_META | _SIGNATURE_CLIENT_META | frozenset({"reason"}),
    ),
    ACTION_SIGNATURE_REQUEST_SIGNED: ActionPolicy(
        metadata_required=frozenset({"client_record_id", "signer_name"}),
        metadata_allowed=_SIGNATURE_BASE_META | _SIGNATURE_CLIENT_META | _SIGNATURE_SIGNED_META,
    ),
    ACTION_SIGNATURE_REQUEST_CANCELED: ActionPolicy(
        metadata_required=frozenset({"client_record_id", "signer_name"}),
        metadata_allowed=_SIGNATURE_BASE_META | frozenset({"reason"}),
    ),
    ACTION_SIGNATURE_REQUEST_EXPIRED: ActionPolicy(
        metadata_required=frozenset({"client_record_id", "signer_name"}),
        metadata_allowed=_SIGNATURE_BASE_META | frozenset({"reason"}),
    ),
    # note
    ACTION_NOTE_CREATED: ActionPolicy(
        value_fields=_NOTE_FIELDS,
        metadata_required=frozenset({"client_record_id", "note_id", "entity_type", "entity_id"}),
        metadata_allowed=_NOTE_META,
    ),
    ACTION_NOTE_UPDATED: ActionPolicy(
        value_fields=_NOTE_FIELDS,
        metadata_required=frozenset({"client_record_id", "note_id", "entity_type", "entity_id"}),
        metadata_allowed=_NOTE_META,
    ),
    ACTION_NOTE_DELETED: ActionPolicy(
        value_fields=_NOTE_FIELDS,
        metadata_required=frozenset({"client_record_id", "note_id", "entity_type", "entity_id"}),
        metadata_allowed=_NOTE_META,
    ),
    # task
    ACTION_TASK_CREATED: ActionPolicy(
        value_fields=_TASK_FIELDS,
        metadata_required=frozenset(),
        metadata_allowed=_TASK_META,
    ),
    ACTION_TASK_UPDATED: ActionPolicy(
        value_fields=_TASK_FIELDS,
        metadata_required=frozenset(),
        metadata_allowed=_TASK_META,
    ),
    ACTION_TASK_ASSIGNED: ActionPolicy(
        value_fields=frozenset({"assigned_to_user_id"}),
        metadata_required=frozenset(),
        metadata_allowed=_TASK_META,
    ),
    ACTION_TASK_COMPLETED: ActionPolicy(
        value_fields=_STATUS_ONLY,
        metadata_required=frozenset(),
        metadata_allowed=_TASK_META,
    ),
    ACTION_TASK_CANCELED: ActionPolicy(
        value_fields=_STATUS_ONLY,
        metadata_required=frozenset(),
        metadata_allowed=_TASK_META,
    ),
    ACTION_TASK_DELETED: ActionPolicy(
        value_fields=_TASK_FIELDS,
        metadata_required=frozenset(),
        metadata_allowed=_TASK_META,
    ),
    # correspondence
    ACTION_CORRESPONDENCE_CREATED: ActionPolicy(
        value_fields=_CORRESPONDENCE_FIELDS,
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_CORRESPONDENCE_META,
    ),
    ACTION_CORRESPONDENCE_UPDATED: ActionPolicy(
        value_fields=_CORRESPONDENCE_FIELDS,
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_CORRESPONDENCE_META,
    ),
    ACTION_CORRESPONDENCE_DELETED: ActionPolicy(
        value_fields=_CORRESPONDENCE_FIELDS,
        metadata_required=frozenset({"client_record_id"}),
        metadata_allowed=_CORRESPONDENCE_META,
    ),
    # notification
    ACTION_NOTIFICATION_SENT: ActionPolicy(
        value_fields=_NOTIFICATION_FIELDS,
        metadata_required=frozenset({"client_record_id", "trigger", "channel"}),
        metadata_allowed=_NOTIFICATION_META,
    ),
    # reminder
    ACTION_REMINDER_CREATED: ActionPolicy(
        value_fields=_REMINDER_FIELDS,
        metadata_required=frozenset({"action_type"}),
        metadata_allowed=_REMINDER_META,
    ),
    ACTION_REMINDER_CANCELED: ActionPolicy(
        value_fields=_STATUS_ONLY,
        metadata_required=frozenset({"action_type"}),
        metadata_allowed=_REMINDER_META,
    ),
    ACTION_REMINDER_FIRED: ActionPolicy(
        value_fields=_STATUS_ONLY,
        metadata_required=frozenset({"action_type"}),
        metadata_allowed=_REMINDER_META,
    ),
    ACTION_REMINDER_FAILED: ActionPolicy(
        value_fields=frozenset({"status", "failure_reason"}),
        metadata_required=frozenset({"action_type"}),
        metadata_allowed=_REMINDER_META,
    ),
    # tax_calendar
    ACTION_TAX_CALENDAR_GENERATED: ActionPolicy(
        value_fields=_TAX_CALENDAR_FIELDS,
        metadata_required=frozenset({"start_year", "end_year"}),
        metadata_allowed=_TAX_CALENDAR_META,
    ),
}


def _fail(message: str, code: ErrorCode) -> NoReturn:
    raise AppError(message, code, status_code=500)


def validate_actor(
    actor_type: str, performed_by: int | None, actor_display_name: str | None
) -> None:
    """Enforce the §5a actor matrix; raise on any invalid combination.

    Phase-2 decision (see docs/audit-refactor-progress.md): structural invariants
    are fail-closed for all actor types (`actor_type` valid; `user ⇒ performed_by`;
    `system`/`external_signer ⇒ performed_by NULL + display required). For `user`
    rows `actor_display_name` is encouraged but NOT fail-closed — the `performed_by`
    FK gives a read-time fallback; strict enforcement + universal name-threading is
    a tracked follow-up (plan §5a follow-up).
    """
    if actor_type not in VALID_ACTOR_TYPES:
        _fail(f"Unknown audit actor_type: {actor_type!r}", ErrorCode.AUDIT_INVALID_ACTOR)
    if actor_type == "user":
        if performed_by is None:
            _fail("actor_type=user requires performed_by", ErrorCode.AUDIT_INVALID_ACTOR)
        return
    if performed_by is not None:
        _fail(
            f"actor_type={actor_type} must have performed_by=None",
            ErrorCode.AUDIT_INVALID_ACTOR,
        )
    if not actor_display_name:
        _fail(
            f"actor_display_name is required for actor_type={actor_type}",
            ErrorCode.AUDIT_INVALID_ACTOR,
        )


def _assert_no_forbidden_fields(value: Any) -> None:
    if isinstance(value, (bytes, bytearray)):
        _fail("Raw bytes are not allowed in audit payloads", ErrorCode.AUDIT_FORBIDDEN_FIELD)
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in _FORBIDDEN_KEY_SUBSTRINGS):
                _fail(f"Forbidden field in audit payload: {key!r}", ErrorCode.AUDIT_FORBIDDEN_FIELD)
            _assert_no_forbidden_fields(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_forbidden_fields(item)


def _top_level_keys(value: Any) -> set[str]:
    return set(value.keys()) if isinstance(value, dict) else set()


def _compact_bytes(value: Any) -> int:
    return len(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _assert_within(value: Any, cap: int, label: str) -> None:
    if value is None:
        return
    size = _compact_bytes(value)
    if size > cap:
        _fail(f"Audit {label} exceeds {cap} bytes (got {size})", ErrorCode.AUDIT_PAYLOAD_TOO_LARGE)


def validate_payload(
    entity_type: str,
    action: str,
    old_value: Any,
    new_value: Any,
    metadata_json: Any,
) -> None:
    """Enforce §16 on already-normalized (JSON-safe) payload values."""
    # Namespace must match the row's entity_type.
    if action.split(".", 1)[0] != entity_type:
        _fail(
            f"Action {action!r} does not match entity_type {entity_type!r}",
            ErrorCode.AUDIT_FORBIDDEN_FIELD,
        )

    policy = ACTION_POLICIES.get(action)
    if policy is None:
        _fail(
            f"No audit policy registered for action {action!r}", ErrorCode.AUDIT_INVALID_ENTITY_TYPE
        )

    # Recursive denylist + raw bytes (defense-in-depth).
    for value in (old_value, new_value, metadata_json):
        _assert_no_forbidden_fields(value)

    # Positive value-field allowlist for old_value/new_value (top-level keys).
    extra_values = (_top_level_keys(old_value) | _top_level_keys(new_value)) - policy.value_fields
    if extra_values:
        _fail(
            f"Non-allowlisted value field(s) for {action}: {sorted(extra_values)}",
            ErrorCode.AUDIT_FORBIDDEN_FIELD,
        )

    # metadata must be an object (never a list/scalar that silently bypasses).
    if metadata_json is not None and not isinstance(metadata_json, dict):
        _fail(
            f"metadata_json must be an object for {action}",
            ErrorCode.AUDIT_FORBIDDEN_FIELD,
        )
    meta_keys = _top_level_keys(metadata_json)
    extra_meta = meta_keys - policy.metadata_allowed
    if extra_meta:
        _fail(
            f"Non-allowlisted metadata field(s) for {action}: {sorted(extra_meta)}",
            ErrorCode.AUDIT_FORBIDDEN_FIELD,
        )
    missing_meta = policy.metadata_required - meta_keys
    if missing_meta:
        _fail(
            f"Missing required metadata field(s) for {action}: {sorted(missing_meta)}",
            ErrorCode.AUDIT_FORBIDDEN_FIELD,
        )

    if action == ACTION_SIGNATURE_REQUEST_SIGNED:
        assert isinstance(metadata_json, dict)  # required metadata above guarantees an object
        has_hash = bool(metadata_json.get("content_hash"))
        hash_missing = metadata_json.get("content_hash_missing") is True
        if has_hash == hash_missing:
            _fail(
                "signature_request.signed requires content_hash or content_hash_missing=true",
                ErrorCode.AUDIT_FORBIDDEN_FIELD,
            )

    _assert_within(old_value, OLD_NEW_VALUE_MAX_BYTES, "old_value")
    _assert_within(new_value, OLD_NEW_VALUE_MAX_BYTES, "new_value")
    _assert_within(metadata_json, METADATA_MAX_BYTES, "metadata_json")
