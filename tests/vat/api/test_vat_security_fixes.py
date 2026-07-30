"""
Security-fix regression tests for F-007, F-008, F-009, F-010.
Each test targets exactly one invariant; failure message names the finding.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.businesses.models.business import BusinessStatus
from app.common.enums import IdNumberType, ObligationStatus
from app.core.exceptions import AppError
from app.vat.models.vat_work_item import VatWorkItem
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


def test_an_open_amendment_cannot_be_deleted(client, advisor_headers, vat_client, test_user):
    """Deleting the tip would leave the period with no visible row at all.

    An amendment is born open, so the status gate lets it through: the original
    keeps its ``superseded_at`` stamp and would be hidden as corrected while the
    amendment is hidden as deleted — and the period could then be neither amended
    again nor recreated.
    """
    item_id = setup_ready_item(
        client, advisor_headers, vat_client, "2026-02", assigned_to=test_user.id
    )
    assert (
        client.post(
            f"/api/v1/vat/work-items/{item_id}/file",
            headers=advisor_headers,
            json={"submission_method": "online"},
        ).status_code
        == 200
    )
    amendment = client.post(f"/api/v1/vat/work-items/{item_id}/amend", headers=advisor_headers)
    assert amendment.status_code == 201
    amendment_id = amendment.json()["id"]

    resp = client.delete(f"/api/v1/vat/work-items/{amendment_id}", headers=advisor_headers)

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "OBLIGATION.AMENDMENT_NOT_DELETABLE"
    # The tip survives, so the period is still one visible row.
    assert (
        client.get(f"/api/v1/vat/work-items/{amendment_id}", headers=advisor_headers).status_code
        == 200
    )


def _file_and_amend(client, headers, vat_client, period, assigned_to):
    """A closed period with an open correction: ``(original_id, amendment_id)``."""
    item_id = setup_ready_item(client, headers, vat_client, period, assigned_to=assigned_to)
    assert (
        client.post(
            f"/api/v1/vat/work-items/{item_id}/file",
            headers=headers,
            json={"submission_method": "online"},
        ).status_code
        == 200
    )
    amendment = client.post(f"/api/v1/vat/work-items/{item_id}/amend", headers=headers)
    assert amendment.status_code == 201
    return item_id, amendment.json()["id"]


def test_withdrawing_an_amendment_restores_the_original_and_frees_the_chain(
    client, advisor_headers, vat_client, test_user
):
    """The whole point of the act: the period comes back, and can be corrected again.

    The second amendment is what proves the ``amends_id`` slot was freed — its
    unique index excludes deleted rows only, so a withdrawal that moved the
    correction to ``CANCELED`` instead would fail here on a unique violation.
    """
    original_id, amendment_id = _file_and_amend(
        client, advisor_headers, vat_client, "2026-03", test_user.id
    )

    resp = client.post(f"/api/v1/vat/work-items/{amendment_id}/withdraw", headers=advisor_headers)

    assert resp.status_code == 200
    # The restored original is returned, closed and no longer corrected.
    body = resp.json()
    assert body["id"] == original_id
    assert body["status"] == ObligationStatus.SUBMITTED.value
    assert body["superseded_at"] is None
    assert body["amends_id"] is None

    # It is the period's one visible row again...
    assert (
        client.get(f"/api/v1/vat/work-items/{amendment_id}", headers=advisor_headers).status_code
        == 404
    )
    # ...and it can be corrected again, which the unique index on amends_id would
    # refuse if the withdrawn row still held the slot.
    again = client.post(f"/api/v1/vat/work-items/{original_id}/amend", headers=advisor_headers)
    assert again.status_code == 201
    assert again.json()["amends_id"] == original_id


def test_a_withdrawn_amendment_stays_in_the_chain(client, advisor_headers, vat_client, test_user):
    """The one read that shows what happened, not what counts."""
    original_id, amendment_id = _file_and_amend(
        client, advisor_headers, vat_client, "2026-04", test_user.id
    )
    assert (
        client.post(
            f"/api/v1/vat/work-items/{amendment_id}/withdraw", headers=advisor_headers
        ).status_code
        == 200
    )

    chain = client.get(f"/api/v1/vat/work-items/{original_id}/chain", headers=advisor_headers)

    assert chain.status_code == 200
    records = {record["id"]: record for record in chain.json()}
    assert set(records) == {original_id, amendment_id}
    assert records[amendment_id]["is_withdrawn"] is True
    assert records[original_id]["is_withdrawn"] is False
    assert records[original_id]["superseded_at"] is None


def test_withdrawing_a_record_that_is_not_an_amendment_is_rejected(
    client, advisor_headers, vat_client, test_user
):
    """Withdrawing undoes a link; a standalone record has none to undo."""
    item_id = setup_ready_item(
        client, advisor_headers, vat_client, "2026-05", assigned_to=test_user.id
    )

    resp = client.post(f"/api/v1/vat/work-items/{item_id}/withdraw", headers=advisor_headers)

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OBLIGATION.NOT_AN_AMENDMENT"


def test_a_filed_amendment_cannot_be_withdrawn(client, advisor_headers, vat_client, test_user):
    """Once a correction is filed it is the record of a filing (D-13)."""
    _original_id, amendment_id = _file_and_amend(
        client, advisor_headers, vat_client, "2026-06", test_user.id
    )
    _add_invoice(client, advisor_headers, amendment_id, "INV-WITHDRAW-1")
    _ready(client, advisor_headers, amendment_id)
    assert (
        client.post(
            f"/api/v1/vat/work-items/{amendment_id}/file",
            headers=advisor_headers,
            json={"submission_method": "online"},
        ).status_code
        == 200
    )

    resp = client.post(f"/api/v1/vat/work-items/{amendment_id}/withdraw", headers=advisor_headers)

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OBLIGATION.LOCKED"


def test_a_middle_link_of_a_chain_cannot_be_withdrawn(
    client, advisor_headers, vat_client, test_user
):
    """On ``original ← A ← B``, taking back ``A`` would give the period two tips.

    It is refused as ``LOCKED`` rather than by the tip check, and that is not an
    accident: a record can only be amended once it is filed, and ``submitted`` has
    no way out — so a superseded row is always a filed row, and the closed gate
    always answers first. The tip check in ``assert_withdrawable`` is the
    invariant behind that reasoning, kept for the day the reasoning changes.
    """
    _original_id, first_id = _file_and_amend(
        client, advisor_headers, vat_client, "2026-07", test_user.id
    )
    _add_invoice(client, advisor_headers, first_id, "INV-WITHDRAW-2")
    _ready(client, advisor_headers, first_id)
    assert (
        client.post(
            f"/api/v1/vat/work-items/{first_id}/file",
            headers=advisor_headers,
            json={"submission_method": "online"},
        ).status_code
        == 200
    )
    second = client.post(f"/api/v1/vat/work-items/{first_id}/amend", headers=advisor_headers)
    assert second.status_code == 201

    resp = client.post(f"/api/v1/vat/work-items/{first_id}/withdraw", headers=advisor_headers)

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OBLIGATION.LOCKED"


def test_a_filing_that_lands_before_the_lock_stops_the_withdrawal(
    client, test_db, advisor_headers, vat_client, test_user
):
    """The re-check after the lock has to see the DB, not what was read before it.

    The service reads the correction, locks it, then checks it again — the second
    check exists for the filing that lands while it waits for the lock. The setup
    here recreates the only thing that makes that check meaningful: the correction
    is already in the session's identity map as ``in_progress`` when the request
    starts, and the DB says ``submitted``. A locked read that does not repopulate
    hands back the identity-mapped row, the re-check passes on the state it was
    already told not to trust, and a filed record is removed.

    A true two-transaction race cannot be staged here — the suite runs one
    connection inside one transaction — so this drives the same divergence
    directly. ``test_get_by_id_for_update_refreshes_a_row_already_in_the_identity_map``
    covers the repository half.
    """
    _original_id, amendment_id = _file_and_amend(
        client, advisor_headers, vat_client, "2026-08", test_user.id
    )
    # Load it, then move it underneath the ORM: the object keeps the status it was
    # loaded with, exactly as it would while another transaction files the period.
    stale = test_db.get(VatWorkItem, amendment_id)
    assert stale is not None and stale.status == ObligationStatus.IN_PROGRESS
    test_db.execute(
        text("UPDATE vat_work_items SET status = :status WHERE id = :id"),
        {"status": ObligationStatus.SUBMITTED.value, "id": amendment_id},
    )
    assert stale.status == ObligationStatus.IN_PROGRESS

    resp = client.post(f"/api/v1/vat/work-items/{amendment_id}/withdraw", headers=advisor_headers)

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OBLIGATION.LOCKED"


def test_a_canceled_amendment_can_be_withdrawn(
    client, test_db, advisor_headers, vat_client, test_user
):
    """Cancelling is terminal but it is not a filing, so there is nothing to protect.

    It also has to be allowed: a cancelled correction keeps ``superseded_at IS
    NULL`` for ever, so it stays its period's tip while the filed record it
    corrected stays hidden — withdrawing is the only way back out.
    """
    original_id, amendment_id = _file_and_amend(
        client, advisor_headers, vat_client, "2026-09", test_user.id
    )
    test_db.execute(
        text("UPDATE vat_work_items SET status = :status WHERE id = :id"),
        {"status": ObligationStatus.CANCELED.value, "id": amendment_id},
    )

    resp = client.post(f"/api/v1/vat/work-items/{amendment_id}/withdraw", headers=advisor_headers)

    assert resp.status_code == 200
    assert resp.json()["id"] == original_id
    assert resp.json()["superseded_at"] is None
