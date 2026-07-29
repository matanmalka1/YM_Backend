"""
Security-fix regression tests for F-007, F-008, F-009, F-010.
Each test targets exactly one invariant; failure message names the finding.
"""

from types import SimpleNamespace

import pytest

from app.businesses.models.business import BusinessStatus
from app.common.enums import IdNumberType, ObligationStatus
from app.core.exceptions import AppError
from app.vat.services.vat_data_entry_invoice_update_service import update_invoice
from tests.vat.api.test_vat_reports_utils import (
    create_work_item,
    income_payload,
    setup_ready_item,
)


def _add_invoice(client, headers, item_id, invoice_number="INV-SEC-1"):
    resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/invoices",
        headers=headers,
        json=income_payload(invoice_number=invoice_number),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _ready(client, headers, item_id):
    resp = client.post(f"/api/v1/vat/work-items/{item_id}/ready-for-review", headers=headers)
    assert resp.status_code == 200


# ── F-007: Filing requires assigned_to ────────────────────────────────────────


def test_f007_filing_without_assignee_is_rejected(client, advisor_headers, vat_client):
    """F-007: item with no assigned_to must not transition to filed."""
    item_id = create_work_item(client, advisor_headers, vat_client, "2025-07")
    _add_invoice(client, advisor_headers, item_id, "INV-F007-1")
    _ready(client, advisor_headers, item_id)

    resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/file",
        headers=advisor_headers,
        json={"submission_method": "online"},
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VAT.ASSIGNEE_REQUIRED"


def test_f007_filing_with_assignee_succeeds(client, advisor_headers, vat_client, test_user):
    """F-007: item with assigned_to set must be fileable."""
    item_id = setup_ready_item(
        client, advisor_headers, vat_client, "2025-08", assigned_to=test_user.id
    )

    resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/file",
        headers=advisor_headers,
        json={"submission_method": "online"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "submitted"


# ── F-008: business_activity_id ownership check on invoice update ─────────────


def test_f008_update_invoice_rejects_activity_from_other_entity(
    client, advisor_headers, vat_client, test_user, client_factory, business_factory
):
    """F-008: updating an invoice with a business_activity_id from another legal entity must fail."""
    other_client = client_factory(
        full_name="Other Entity Client",
        id_number="987654321",
        id_number_type=IdNumberType.INDIVIDUAL,
    )
    other_business = business_factory(
        legal_entity_id=other_client.legal_entity_id,
        business_name="Other Business",
        status=BusinessStatus.ACTIVE,
        commit=True,
    )

    item_id = create_work_item(client, advisor_headers, vat_client, "2025-09")
    invoice_id = _add_invoice(client, advisor_headers, item_id, "INV-F008-1")

    resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={"business_activity_id": other_business.id},
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "BUSINESS_ACTIVITY.NOT_FOUND"


def test_f008_update_invoice_accepts_activity_from_same_entity(
    client, advisor_headers, vat_client, test_user, business_factory
):
    """F-008: updating with a business_activity_id from the same legal entity must succeed."""
    from datetime import date

    same_entity_business = business_factory(
        legal_entity_id=vat_client.legal_entity_id,
        business_name="Same Entity Second Business",
        status=BusinessStatus.ACTIVE,
        opened_at=date.today(),
        commit=True,
    )

    item_id = create_work_item(client, advisor_headers, vat_client, "2025-10")
    invoice_id = _add_invoice(client, advisor_headers, item_id, "INV-F008-2")

    resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={"business_activity_id": same_entity_business.id},
    )

    assert resp.status_code == 200


# ── F-009: Error codes use DOMAIN.REASON format ───────────────────────────────


def test_update_invoice_raises_vat_net_not_positive_code():
    """F-009: update_invoice service raises VAT.NET_NOT_POSITIVE (not the old bare INVALID_NET_AMOUNT).
    Tested at service level because Pydantic schema catches negative gross before the API layer."""
    item = SimpleNamespace(
        id=1,
        client_record_id=1,
        period="2026-01",
        status=ObligationStatus.IN_PROGRESS,
        deleted_at=None,
    )
    invoice = SimpleNamespace(
        id=1,
        work_item_id=1,
        invoice_number="INV-X",
        invoice_type="income",
        rate_type="standard",
        net_amount=100,
        vat_amount=18,
        is_exceptional=False,
    )
    work_item_repo = SimpleNamespace(
        db=None,
        get_by_id=lambda _id: item,
    )
    invoice_repo = SimpleNamespace(
        get_by_id=lambda _id: invoice,
        get_by_number=lambda *a: None,
    )

    with pytest.raises(AppError) as exc_info:
        update_invoice(
            work_item_repo,
            invoice_repo,
            item_id=1,
            invoice_id=1,
            performed_by=1,
            patch={"gross_amount": -100.0},
        )

    assert exc_info.value.code == "VAT.NET_NOT_POSITIVE"


# ── Amendment: an act on a closed record, not a flag at filing time ──────────
#
# The filing-time flag these tests used to exercise was deleted in W4: it was set
# on a row that already existed, and a second row for the period could never be
# created, so VAT's amendment was unreachable rather than merely unused (§4.1.6).
# What is worth guarding now is that the new act refuses the two states it must.


def test_amending_an_open_period_is_rejected(client, advisor_headers, vat_client, test_user):
    """Only a closed record can be corrected — an open one is simply edited."""
    item_id = setup_ready_item(
        client, advisor_headers, vat_client, "2025-12", assigned_to=test_user.id
    )

    resp = client.post(f"/api/v1/vat/work-items/{item_id}/amend", headers=advisor_headers)

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OBLIGATION.NOT_CLOSED"


def test_a_period_can_be_amended_only_once(client, advisor_headers, vat_client, test_user):
    """A chain is a line, not a tree: two tips would put every aggregate back
    where D-12 found it."""
    item_id = setup_ready_item(
        client, advisor_headers, vat_client, "2026-01", assigned_to=test_user.id
    )
    assert (
        client.post(
            f"/api/v1/vat/work-items/{item_id}/file",
            headers=advisor_headers,
            json={"submission_method": "online"},
        ).status_code
        == 200
    )

    first = client.post(f"/api/v1/vat/work-items/{item_id}/amend", headers=advisor_headers)
    assert first.status_code == 201
    assert first.json()["amends_id"] == item_id

    second = client.post(f"/api/v1/vat/work-items/{item_id}/amend", headers=advisor_headers)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "OBLIGATION.ALREADY_AMENDED"
