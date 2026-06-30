"""AuditEntityRegistry — declarative descriptors for every audited entity_type.

The registry is the single source of truth for which entity types the generic
audit read route accepts (``ALLOWED_READ_ENTITY_TYPES`` is derived from it, never
hand-maintained) and how each one's client context / existence is resolved.

Descriptors are pure data: they name the SQLAlchemy model, a resolution
*strategy*, and a sensitivity flag. They execute NO SQL. The actual lookups run
in :class:`app.audit.repositories.audit_scope_repository.AuditScopeRepository`
(repositories do DB access only); :class:`AuditTrailService` orchestrates them.

Scope is NOT authorization: both ADVISOR and SECRETARY may read audit history,
and audit reads bypass the active-client filter so soft/hard-deleted history
stays readable. ``client_ids`` is contextual metadata, not an access gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.advance_payments.models.advance_payment import AdvancePayment
from app.annual_reports.models.annual_report_model import AnnualReport
from app.audit.audit_constants import (
    ENTITY_ADVANCE_PAYMENT,
    ENTITY_ANNUAL_REPORT,
    ENTITY_AUTHORITY_CONTACT,
    ENTITY_BINDER,
    ENTITY_BINDER_HANDOVER,
    ENTITY_BINDER_INTAKE,
    ENTITY_BUSINESS,
    ENTITY_CHARGE,
    ENTITY_CLIENT,
    ENTITY_CORRESPONDENCE,
    ENTITY_DOCUMENT,
    ENTITY_INVOICE,
    ENTITY_LEGAL_ENTITY,
    ENTITY_NOTE,
    ENTITY_NOTIFICATION,
    ENTITY_PERSON,
    ENTITY_PERSON_LEGAL_ENTITY_LINK,
    ENTITY_REMINDER,
    ENTITY_SIGNATURE_REQUEST,
    ENTITY_TASK,
    ENTITY_TAX_CALENDAR,
    ENTITY_VAT_INVOICE,
    ENTITY_VAT_WORK_ITEM,
)
from app.authority_contacts.models.authority_contact import AuthorityContact
from app.binders.models.binder import Binder
from app.binders.models.binder_handover import BinderHandover
from app.binders.models.binder_intake import BinderIntake
from app.businesses.models.business import Business
from app.charges.models.charge import Charge
from app.clients.models.client_record import ClientRecord
from app.communications.models.correspondence import Correspondence
from app.documents.permanent_documents.models.permanent_document import PermanentDocument
from app.invoices.models.invoice import Invoice
from app.legal_entities.models.legal_entity import LegalEntity
from app.legal_entities.models.person import Person
from app.legal_entities.models.person_legal_entity_link import PersonLegalEntityLink
from app.notes.models.note_entity_note import EntityNote
from app.notifications.models.notification import Notification
from app.reminders.models.reminder import Reminder
from app.signature_requests.models.signature_request import SignatureRequest
from app.tasks.models.task import Task
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry
from app.vat.models.vat_invoice import VatInvoice
from app.vat.models.vat_work_item import VatWorkItem


class ScopeStrategy:
    """How an entity_type's owning client(s) / existence are resolved."""

    SELF = "self"  # the entity row *is* the client record
    CLIENT_COLUMN = "client_column"  # model has a client_record_id column
    VIA_LEGAL_ENTITY = "via_legal_entity"  # legal_entity_id -> client_records (multi)
    LEGAL_ENTITY = "legal_entity"  # the row is a legal_entity -> client_records (multi)
    PERSON = "person"  # person -> links -> legal_entities -> client_records (multi)
    PERSON_LINK = "person_link"  # link.legal_entity_id -> client_records (multi)
    VIA_CHARGE = "via_charge"  # charge_id -> charge.client_record_id
    VIA_WORK_ITEM = "via_work_item"  # work_item_id -> vat_work_item.client_record_id
    VIA_BINDER = "via_binder"  # binder_id -> binder.client_record_id
    NOTE = "note"  # polymorphic entity_type/entity_id (best-effort)
    REMINDER = "reminder"  # source_domain/source_id (best-effort)
    FIRM_LEVEL = "firm_level"  # firm-wide, no owning client


@dataclass(frozen=True)
class AuditEntityDescriptor:
    entity_type: str
    model: type[Any]
    strategy: str
    sensitive: bool = False
    # Audit carries restricted forensic/PII for sensitive types (§16); under the
    # current two-role model both roles see the same allowed fields (§14).
    sensitive_metadata_fields: frozenset[str] = field(default_factory=frozenset)


_DESCRIPTORS: tuple[AuditEntityDescriptor, ...] = (
    AuditEntityDescriptor(ENTITY_CLIENT, ClientRecord, ScopeStrategy.SELF),
    AuditEntityDescriptor(ENTITY_BUSINESS, Business, ScopeStrategy.VIA_LEGAL_ENTITY),
    AuditEntityDescriptor(ENTITY_LEGAL_ENTITY, LegalEntity, ScopeStrategy.LEGAL_ENTITY),
    AuditEntityDescriptor(ENTITY_PERSON, Person, ScopeStrategy.PERSON),
    AuditEntityDescriptor(
        ENTITY_PERSON_LEGAL_ENTITY_LINK, PersonLegalEntityLink, ScopeStrategy.PERSON_LINK
    ),
    AuditEntityDescriptor(ENTITY_AUTHORITY_CONTACT, AuthorityContact, ScopeStrategy.CLIENT_COLUMN),
    AuditEntityDescriptor(ENTITY_NOTE, EntityNote, ScopeStrategy.NOTE),
    AuditEntityDescriptor(ENTITY_ADVANCE_PAYMENT, AdvancePayment, ScopeStrategy.CLIENT_COLUMN),
    AuditEntityDescriptor(ENTITY_CHARGE, Charge, ScopeStrategy.CLIENT_COLUMN),
    AuditEntityDescriptor(ENTITY_INVOICE, Invoice, ScopeStrategy.VIA_CHARGE),
    AuditEntityDescriptor(ENTITY_VAT_WORK_ITEM, VatWorkItem, ScopeStrategy.CLIENT_COLUMN),
    AuditEntityDescriptor(ENTITY_VAT_INVOICE, VatInvoice, ScopeStrategy.VIA_WORK_ITEM),
    AuditEntityDescriptor(ENTITY_ANNUAL_REPORT, AnnualReport, ScopeStrategy.CLIENT_COLUMN),
    AuditEntityDescriptor(ENTITY_BINDER, Binder, ScopeStrategy.CLIENT_COLUMN),
    AuditEntityDescriptor(ENTITY_BINDER_INTAKE, BinderIntake, ScopeStrategy.VIA_BINDER),
    AuditEntityDescriptor(ENTITY_BINDER_HANDOVER, BinderHandover, ScopeStrategy.CLIENT_COLUMN),
    AuditEntityDescriptor(ENTITY_DOCUMENT, PermanentDocument, ScopeStrategy.CLIENT_COLUMN),
    AuditEntityDescriptor(
        ENTITY_SIGNATURE_REQUEST,
        SignatureRequest,
        ScopeStrategy.CLIENT_COLUMN,
        sensitive=True,
        sensitive_metadata_fields=frozenset(
            {"ip_address", "user_agent", "content_hash", "signed_document_key", "signer_email"}
        ),
    ),
    AuditEntityDescriptor(ENTITY_TASK, Task, ScopeStrategy.CLIENT_COLUMN),
    AuditEntityDescriptor(ENTITY_CORRESPONDENCE, Correspondence, ScopeStrategy.CLIENT_COLUMN),
    AuditEntityDescriptor(ENTITY_NOTIFICATION, Notification, ScopeStrategy.CLIENT_COLUMN),
    AuditEntityDescriptor(ENTITY_REMINDER, Reminder, ScopeStrategy.REMINDER),
    AuditEntityDescriptor(ENTITY_TAX_CALENDAR, TaxCalendarEntry, ScopeStrategy.FIRM_LEVEL),
)

# deadline_rule is intentionally EXCLUDED: code review confirms it has no per-row
# UI edit route (only list + a firm-wide bootstrap), so it is not independently
# audited/read in the current model (plan §6 "conditional").

AUDIT_ENTITY_REGISTRY: dict[str, AuditEntityDescriptor] = {d.entity_type: d for d in _DESCRIPTORS}


def get_descriptor(entity_type: str) -> AuditEntityDescriptor | None:
    return AUDIT_ENTITY_REGISTRY.get(entity_type)


def allowed_read_entity_types() -> frozenset[str]:
    """Derived from the registry — never hand-maintained (§3a/§6)."""
    return frozenset(AUDIT_ENTITY_REGISTRY)
