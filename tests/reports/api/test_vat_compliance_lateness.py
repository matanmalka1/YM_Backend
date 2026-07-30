"""The VAT compliance report reads the stored lateness, it does not re-derive it.

Whether a period was filed late is decided once, at the close (D-20), and
``chain_closed_late`` keeps that answer across corrections (D-34). The report
used to ask the question again — ``closed_at`` against ``due_date_effective`` —
and an amendment has no due date, so a corrected period fell out of both counts
and a late filing quietly stopped being late.
"""

from datetime import date

from app.common.enums import ObligationStatus, ObligationType, SubmissionMethod, VatType
from app.vat.models.vat_work_item import VatWorkItem
from app.vat.repositories.vat_work_item_write_repository import VatWorkItemWriteRepository
from tests.helpers.tax_calendar_links import (
    create_linked_vat_work_item,
    create_tax_calendar_entry_for_period,
)

REPORT = "/api/v1/reports/vat-compliance?year=2026"
#: Deadline 2026-02-16 — long past, so a close now is late.
LATE_PERIOD = "2026-01"


def _file(test_db, item_id: int, actor_id: int):
    VatWorkItemWriteRepository(test_db).mark_filed(
        item_id,
        final_vat_amount=100.0,
        submission_method=SubmissionMethod.ONLINE,
        closed_by=actor_id,
    )
    test_db.commit()


def _row(client, headers):
    resp = client.get(REPORT, headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    return items[0]


def _late_filed_item(test_db, client_record_id: int, actor_id: int):
    item = create_linked_vat_work_item(
        test_db,
        period_type=VatType.MONTHLY,
        client_record_id=client_record_id,
        created_by=actor_id,
        period=LATE_PERIOD,
        status=ObligationStatus.INPUT_RECEIVED,
    )
    _file(test_db, item.id, actor_id)
    assert item.closed_late is True
    return item


def test_a_corrected_late_period_is_still_counted_late(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _ = create_client_with_business(
        full_name="Compliance Late Amend", id_number="RPT-LATE-AMEND", opened_at=date(2025, 1, 1)
    )
    item = _late_filed_item(test_db, crm_client.id, test_user.id)

    amendment_id = client.post(
        f"/api/v1/vat/work-items/{item.id}/amend", headers=advisor_headers
    ).json()["id"]
    _file(test_db, amendment_id, test_user.id)

    row = _row(client, advisor_headers)
    assert row["periods_filed"] == 1
    assert row["late_count"] == 1
    assert row["on_time_count"] == 0


def test_every_filed_period_lands_in_exactly_one_bucket(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    """The invariant the old bug broke silently: nothing filed goes uncounted.

    The report reported one filed period and zero on-time-or-late ones, and no
    assertion anywhere disagreed with it.
    """
    crm_client, _ = create_client_with_business(
        full_name="Compliance Buckets", id_number="RPT-BUCKETS", opened_at=date(2025, 1, 1)
    )
    item = _late_filed_item(test_db, crm_client.id, test_user.id)
    amendment_id = client.post(
        f"/api/v1/vat/work-items/{item.id}/amend", headers=advisor_headers
    ).json()["id"]
    _file(test_db, amendment_id, test_user.id)

    row = _row(client, advisor_headers)
    assert row["on_time_count"] + row["late_count"] == row["periods_filed"]


def test_a_period_that_never_had_a_deadline_is_neither_on_time_nor_late(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    """NULL is not False (D-32): a period nobody could miss is not "on time".

    Built against the table on purpose. Every VAT period the application creates
    is linked to a calendar entry and carries a deadline, so this is the shape
    only a row from before that rule could have — and the report has to survive
    it without inventing a performance number.
    """
    crm_client, _ = create_client_with_business(
        full_name="Compliance No Deadline", id_number="RPT-NO-DUE", opened_at=date(2025, 1, 1)
    )
    entry = create_tax_calendar_entry_for_period(test_db, ObligationType.VAT, LATE_PERIOD, 1)
    item = VatWorkItem(
        client_record_id=crm_client.id,
        created_by=test_user.id,
        period=LATE_PERIOD,
        period_type=VatType.MONTHLY,
        status=ObligationStatus.INPUT_RECEIVED,
        tax_calendar_entry_id=entry.id,
    )
    test_db.add(item)
    test_db.flush()
    _file(test_db, item.id, test_user.id)
    assert item.closed_late is None and item.chain_closed_late is None

    row = _row(client, advisor_headers)
    assert row["periods_filed"] == 1
    assert (row["on_time_count"], row["late_count"]) == (0, 0)
