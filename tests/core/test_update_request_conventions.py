"""Schema-level guards shared by all *UpdateRequest schemas (issue 41 + 39).

Tier-1 tests: pure Pydantic validation, no DB. Behavior-level tests for
specific domains live with those domains.
"""

import pytest
from pydantic import ValidationError

from app.advance_payments.schemas.advance_payment import AdvancePaymentUpdateRequest
from app.annual_reports.schemas.annual_report_annex import AnnexDataUpdateRequest
from app.annual_reports.schemas.annual_report_detail import AnnualReportDetailUpdateRequest
from app.annual_reports.schemas.annual_report_financials import (
    ExpenseLineUpdateRequest,
    IncomeLineUpdateRequest,
)
from app.annual_reports.schemas.annual_report_requests import DeadlineUpdateRequest
from app.authority_contacts.schemas.authority_contact import AuthorityContactUpdateRequest
from app.binders.schemas.binder import BinderIntakeUpdateRequest
from app.businesses.schemas.business_schemas import BusinessUpdateRequest
from app.clients.schemas.client_requests import ClientUpdateRequest
from app.communications.schemas.correspondence import CorrespondenceUpdateRequest
from app.notes.schemas.entity_note import EntityNoteUpdateRequest
from app.tasks.schemas.task import TaskUpdateRequest
from app.users.schemas.user_management import UserUpdateRequest
from app.vat.schemas.vat_invoice_update import VatInvoiceUpdateRequest
from app.vat.schemas.vat_report import VatWorkItemUpdateRequest

ALL_UPDATE_SCHEMAS = [
    AdvancePaymentUpdateRequest,
    AnnexDataUpdateRequest,
    AnnualReportDetailUpdateRequest,
    IncomeLineUpdateRequest,
    ExpenseLineUpdateRequest,
    DeadlineUpdateRequest,
    AuthorityContactUpdateRequest,
    BusinessUpdateRequest,
    ClientUpdateRequest,
    CorrespondenceUpdateRequest,
    EntityNoteUpdateRequest,
    TaskUpdateRequest,
    UserUpdateRequest,
    VatInvoiceUpdateRequest,
    VatWorkItemUpdateRequest,
    BinderIntakeUpdateRequest,
]


def test_all_update_schemas_are_guarded():
    # 14 existing + renamed BinderIntakeUpdateRequest + VAT work item = 16.
    assert len(ALL_UPDATE_SCHEMAS) == 16


@pytest.mark.parametrize("schema", ALL_UPDATE_SCHEMAS, ids=lambda s: s.__name__)
def test_empty_patch_is_rejected(schema):
    with pytest.raises(ValidationError):
        schema.model_validate({})


@pytest.mark.parametrize("schema", ALL_UPDATE_SCHEMAS, ids=lambda s: s.__name__)
def test_unknown_field_is_rejected(schema):
    with pytest.raises(ValidationError):
        schema.model_validate({"__definitely_not_a_field__": 1})


# ── Blank/whitespace text rejection (NonBlankStr) ─────────────────────────────


@pytest.mark.parametrize("blank", ["", "   "])
@pytest.mark.parametrize(
    ("schema", "field"),
    [
        (TaskUpdateRequest, "title"),
        (CorrespondenceUpdateRequest, "subject"),
        (BusinessUpdateRequest, "business_name"),
        (AuthorityContactUpdateRequest, "name"),
        (ClientUpdateRequest, "full_name"),
        (EntityNoteUpdateRequest, "note"),
        (UserUpdateRequest, "full_name"),
    ],
    ids=lambda v: v if isinstance(v, str) else v.__name__,
)
def test_business_text_rejects_blank(schema, field, blank):
    with pytest.raises(ValidationError):
        schema.model_validate({field: blank})


def test_task_title_preserves_max_length():
    with pytest.raises(ValidationError):
        TaskUpdateRequest.model_validate({"title": "x" * 501})
    assert TaskUpdateRequest.model_validate({"title": "x" * 500}).title == "x" * 500


def test_business_name_preserves_max_length():
    with pytest.raises(ValidationError):
        BusinessUpdateRequest.model_validate({"business_name": "x" * 101})


# ── Explicit-null rejection on non-nullable fields ────────────────────────────


@pytest.mark.parametrize(
    ("schema", "field"),
    [
        (BusinessUpdateRequest, "status"),
        (TaskUpdateRequest, "priority"),
        (ExpenseLineUpdateRequest, "recognition_rate"),
        (ExpenseLineUpdateRequest, "category"),
        (ExpenseLineUpdateRequest, "amount"),
        (IncomeLineUpdateRequest, "source_type"),
        (IncomeLineUpdateRequest, "amount"),
        (ClientUpdateRequest, "status"),
        (CorrespondenceUpdateRequest, "subject"),
        (AuthorityContactUpdateRequest, "name"),
        (AdvancePaymentUpdateRequest, "status"),
        (DeadlineUpdateRequest, "deadline_type"),
        (UserUpdateRequest, "role"),
        (UserUpdateRequest, "email"),
        (UserUpdateRequest, "full_name"),
        (BinderIntakeUpdateRequest, "received_at"),
        (BinderIntakeUpdateRequest, "binder_id"),
    ],
    ids=lambda v: v if isinstance(v, str) else v.__name__,
)
def test_explicit_null_rejected_for_non_nullable(schema, field):
    with pytest.raises(ValidationError):
        schema.model_validate({field: None})


@pytest.mark.parametrize(
    ("schema", "field"),
    [
        (IncomeLineUpdateRequest, "description"),
        (ExpenseLineUpdateRequest, "description"),
        (AuthorityContactUpdateRequest, "office"),
        (BusinessUpdateRequest, "closed_at"),
        (UserUpdateRequest, "phone"),
        (BinderIntakeUpdateRequest, "notes"),
        (VatWorkItemUpdateRequest, "assigned_to"),
        (VatWorkItemUpdateRequest, "pending_materials_note"),
    ],
    ids=lambda v: v if isinstance(v, str) else v.__name__,
)
def test_explicit_null_accepted_for_nullable(schema, field):
    req = schema.model_validate({field: None})
    assert field in req.model_fields_set
    assert getattr(req, field) is None


def test_deadline_partial_note_only_keeps_type_unset():
    req = DeadlineUpdateRequest.model_validate({"custom_deadline_note": "x"})
    assert "deadline_type" not in req.model_fields_set
    assert req.model_dump(exclude_unset=True) == {"custom_deadline_note": "x"}


def test_user_phone_null_clears_but_role_null_rejected():
    cleared = UserUpdateRequest.model_validate({"phone": None})
    assert cleared.phone is None
    with pytest.raises(ValidationError):
        UserUpdateRequest.model_validate({"role": None})
