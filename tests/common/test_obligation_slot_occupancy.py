"""A period's slot is held by the unique index's rule, not by what a list shows.

Two questions that read alike and are not: "does this period already exist?" is
answered by the partial unique index (§4.1.13 — not deleted, not an amendment,
not cancelled), and "which row does this period show?" by the chain-tip scope.
Creation gates asked the second for both, and were wrong in each direction:

- A cancelled period could never be created again, though D-23 exists precisely
  so a returning client's period can be. The database would have accepted it.
  This is the reachable failure, and it is exercised for all three domains
  because the predicate lives in one place and a domain that stops using it
  fails silently.
- A superseded original is invisible to the chain-tip scope while still holding
  its slot. Through the API the amendment that superseded it is the period's
  visible tip, so the old gate happened to refuse on *that* row instead — right
  answer, wrong reason. The gate is now robust without depending on it, which
  is what the last test here pins.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.annual_reports.repositories.annual_report_report_repository import (
    AnnualReportRootRepository,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.common.enums import AdvancePaymentFrequency, IdNumberType, ObligationStatus, VatType
from app.common.obligation_chain import select_chain
from app.core.exceptions import ConflictError
from app.vat.models.vat_work_item import VatWorkItem
from app.vat.repositories.vat_work_item_repository import VatWorkItemRepository
from app.vat.services.vat_intake_service import create_work_item
from tests.helpers.tax_calendar_links import (
    create_linked_advance_payment,
    create_linked_vat_work_item,
)

PERIOD = "2026-03"
TAX_YEAR = 2026


@pytest.fixture
def vat_client(client_factory):
    return client_factory(
        full_name="Slot Occupancy VAT",
        id_number="SLOT-VAT-001",
        id_number_type=IdNumberType.INDIVIDUAL,
        vat_reporting_frequency=VatType.MONTHLY,
    )


# ── A cancelled row releases the slot (D-23) ─────────────────────────────────


def test_cancelled_vat_period_can_be_created_again(test_db, vat_client, actor_user):
    original = create_linked_vat_work_item(
        test_db,
        client_record_id=vat_client.id,
        period=PERIOD,
        created_by=actor_user.id,
    )
    original.status = ObligationStatus.CANCELED
    test_db.flush()

    replacement = create_work_item(
        VatWorkItemRepository(test_db),
        test_db,
        client_record_id=vat_client.id,
        period=PERIOD,
        created_by=actor_user.id,
    )

    assert replacement.id != original.id
    assert replacement.status == ObligationStatus.INPUT_RECEIVED
    # The cancelled attempt stays visible as history — it is not revived, and it
    # is not hidden either.
    chain = test_db.scalars(
        select_chain(
            VatWorkItem,
            client_record_id=vat_client.id,
            period_column=VatWorkItem.period,
            period_value=PERIOD,
        )
    ).all()
    assert [(row.id, row.status) for row in chain] == [
        (original.id, ObligationStatus.CANCELED),
        (replacement.id, ObligationStatus.INPUT_RECEIVED),
    ]


def test_cancelled_annual_year_can_be_created_again(test_db, client_factory, actor_user):
    crm_client = client_factory(
        full_name="Slot Occupancy Annual",
        id_number="SLOT-ANN-001",
        id_number_type=IdNumberType.INDIVIDUAL,
    )
    service = AnnualReportService(test_db)
    original = service.create_report(
        client_record_id=crm_client.id,
        tax_year=TAX_YEAR,
        client_type="individual",
        created_by=actor_user.id,
        created_by_name="Tester",
    )
    original.status = ObligationStatus.CANCELED
    test_db.flush()

    replacement = service.create_report(
        client_record_id=crm_client.id,
        tax_year=TAX_YEAR,
        client_type="individual",
        created_by=actor_user.id,
        created_by_name="Tester",
    )

    assert replacement.id != original.id
    assert replacement.status == ObligationStatus.AWAITING_INPUT


def test_cancelled_advance_period_can_be_created_again(test_db, client_factory, actor_user):
    crm_client = client_factory(
        full_name="Slot Occupancy Advance",
        id_number="SLOT-ADV-001",
        id_number_type=IdNumberType.INDIVIDUAL,
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    original = create_linked_advance_payment(
        test_db,
        client_record_id=crm_client.id,
        period=PERIOD,
        due_date=date(2026, 4, 15),
        expected_amount=Decimal("500.00"),
    )
    original.status = ObligationStatus.CANCELED
    test_db.flush()

    replacement = AdvancePaymentService(test_db).create_payment_for_client(
        client_record_id=crm_client.id,
        period=PERIOD,
        period_months_count=1,
        actor_id=actor_user.id,
    )

    assert replacement.id != original.id


# ── A superseded original still holds the slot ───────────────────────────────


def test_superseded_original_blocks_creation_as_a_conflict_not_a_crash(
    test_db, vat_client, actor_user
):
    """The gate must see the row the index sees, even when nothing shows it.

    ``assert_deletable`` and :func:`withdraw_amendment` together mean the API
    cannot leave a chain with its original superseded and its amendment hidden,
    so this state is built directly against the table. It is still the state the
    gate has to survive: a slot held by a row no list returns. Reading the period
    through the chain-tip scope finds nothing, concludes the period is free, and
    hands the unique index an insert it must reject — an ``IntegrityError``
    surfacing as a 500, where the caller should get a conflict.
    """
    original = create_linked_vat_work_item(
        test_db,
        client_record_id=vat_client.id,
        period=PERIOD,
        created_by=actor_user.id,
        status=ObligationStatus.SUBMITTED,
    )
    amendment = VatWorkItemRepository(test_db).create_amendment(
        original,
        fields={
            "client_record_id": original.client_record_id,
            "period": original.period,
            "period_type": original.period_type,
            "tax_calendar_entry_id": original.tax_calendar_entry_id,
            "status": ObligationStatus.IN_PROGRESS,
            "created_by": actor_user.id,
        },
    )
    test_db.flush()
    assert amendment.amends_id == original.id and original.superseded_at is not None

    # Half of link_amendment undone: the amendment hidden, the stamp left behind.
    test_db.execute(
        text("UPDATE vat_work_items SET deleted_at = now() WHERE id = :id"),
        {"id": amendment.id},
    )
    test_db.expire_all()
    repo = VatWorkItemRepository(test_db)
    assert repo.get_by_client_record_period(vat_client.id, PERIOD) is None
    assert repo.get_slot_occupant_for_period(vat_client.id, PERIOD).id == original.id

    with pytest.raises(ConflictError):
        create_work_item(
            repo,
            test_db,
            client_record_id=vat_client.id,
            period=PERIOD,
            created_by=actor_user.id,
        )


# ── The operational lookup is deterministic ──────────────────────────────────


def test_current_obligation_prefers_the_live_row_under_any_query_plan(
    test_db, vat_client, actor_user
):
    """Ordering, not luck.

    Once a period legitimately holds a cancelled row and a live one, an unordered
    ``.first()`` picks whichever the plan produced first — and it genuinely
    differs: a sequential scan returned the cancelled row while an index scan
    returned the live one. Both plans are forced here.
    """
    cancelled = create_linked_vat_work_item(
        test_db,
        client_record_id=vat_client.id,
        period=PERIOD,
        created_by=actor_user.id,
    )
    cancelled.status = ObligationStatus.CANCELED
    test_db.flush()
    live = create_work_item(
        VatWorkItemRepository(test_db),
        test_db,
        client_record_id=vat_client.id,
        period=PERIOD,
        created_by=actor_user.id,
    )
    test_db.flush()

    repo = VatWorkItemRepository(test_db)
    for scans_enabled in (True, False):
        setting = "on" if scans_enabled else "off"
        test_db.execute(text(f"SET LOCAL enable_indexscan = {setting}"))
        test_db.execute(text(f"SET LOCAL enable_bitmapscan = {setting}"))
        test_db.expire_all()

        found = repo.get_by_client_record_period(vat_client.id, PERIOD)

        assert found is not None
        assert found.id == live.id, f"cancelled row returned with indexscan={setting}"
        assert found.id != cancelled.id

    test_db.execute(text("SET LOCAL enable_indexscan = on"))
    test_db.execute(text("SET LOCAL enable_bitmapscan = on"))


def test_current_obligation_still_shows_a_period_whose_only_row_is_cancelled(
    test_db, vat_client, actor_user
):
    """Cancelled is de-preferred, never filtered — the period must still display."""
    only = create_linked_vat_work_item(
        test_db,
        client_record_id=vat_client.id,
        period=PERIOD,
        created_by=actor_user.id,
    )
    only.status = ObligationStatus.CANCELED
    test_db.flush()

    found = VatWorkItemRepository(test_db).get_by_client_record_period(vat_client.id, PERIOD)

    assert found is not None and found.id == only.id


# ── Re-sync must not touch the cancelled row ─────────────────────────────────


def test_advance_resync_does_not_redate_a_cancelled_payment(test_db, client_factory):
    """Onboarding's re-sync updates cadence and due date on the row it finds.

    Finding the cancelled row means re-dating an obligation the office
    deliberately stopped, which is the same revival D-23 refuses.
    """
    crm_client = client_factory(
        full_name="Slot Occupancy Resync",
        id_number="SLOT-RESYNC-001",
        id_number_type=IdNumberType.INDIVIDUAL,
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    cancelled = create_linked_advance_payment(
        test_db,
        client_record_id=crm_client.id,
        period=PERIOD,
        due_date=date(2026, 4, 15),
        expected_amount=Decimal("500.00"),
    )
    cancelled.status = ObligationStatus.CANCELED
    test_db.flush()

    occupant = AdvancePaymentRepository(test_db).get_slot_occupant_for_period(crm_client.id, PERIOD)

    assert occupant is None, "a cancelled payment must not be offered to the re-sync branch"


def test_annual_slot_query_ignores_cancelled_but_lookup_still_finds_it(
    test_db, client_factory, actor_user
):
    crm_client = client_factory(
        full_name="Slot Occupancy Annual Split",
        id_number="SLOT-ANN-002",
        id_number_type=IdNumberType.INDIVIDUAL,
    )
    report = AnnualReportService(test_db).create_report(
        client_record_id=crm_client.id,
        tax_year=TAX_YEAR,
        client_type="individual",
        created_by=actor_user.id,
        created_by_name="Tester",
    )
    report.status = ObligationStatus.CANCELED
    test_db.flush()

    repo = AnnualReportRootRepository(test_db)

    assert repo.get_slot_occupant_for_year(crm_client.id, TAX_YEAR) is None
    assert repo.get_by_client_record_year(crm_client.id, TAX_YEAR).id == report.id
