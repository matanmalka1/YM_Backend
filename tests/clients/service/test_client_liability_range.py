"""O-7 end to end: an obligation is never created for a span the client owed nothing in.

Before the liability range, onboarding trimmed the plan with
``if entry.due_date < reference_date: continue`` — a *calendar* guard standing in
for a *liability* guard. It was wrong in both directions:

- a client registered in June, onboarded in June, still got a May VAT period,
  because May's due date (15 June) had not passed yet;
- a client onboarded late lost genuinely owed past-due periods.

Neither could be corrected afterwards: the frequency was right, so reconciliation
would keep the row, and D-24 retires the direct DELETE.
"""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.advance_payments.models.advance_payment import AdvancePayment
from app.clients.services.client_create_service import create_client_identity_only
from app.common.enums import AdvancePaymentFrequency, EntityType, IdNumberType, VatType
from app.vat.models.vat_work_item import VatWorkItem

ONBOARDED_ON = date(2026, 6, 10)


def _client(test_db, actor_user, id_number: str, **kwargs):
    return create_client_identity_only(
        test_db,
        full_name="Liability Range Client",
        id_number=id_number,
        id_number_type=IdNumberType.INDIVIDUAL,
        entity_type=EntityType.OSEK_MURSHE,
        vat_reporting_frequency=VatType.MONTHLY,
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
        advance_rate="5.0",
        actor_id=actor_user.id,
        reference_date=ONBOARDED_ON,
        **kwargs,
    )


def _vat_periods(test_db, client_record_id: int) -> list[str]:
    return sorted(
        test_db.scalars(
            select(VatWorkItem.period).where(VatWorkItem.client_record_id == client_record_id)
        )
    )


def _advance_periods(test_db, client_record_id: int) -> list[str]:
    return sorted(
        test_db.scalars(
            select(AdvancePayment.period).where(AdvancePayment.client_record_id == client_record_id)
        )
    )


def test_no_vat_period_before_liability_starts(test_db, actor_user):
    """The exact O-7 case: liable from June, onboarded 10 June, no May period."""
    record = _client(test_db, actor_user, "123456780", vat_liable_from=date(2026, 6, 1))

    periods = _vat_periods(test_db, record.id)

    assert "2026-05" not in periods
    assert periods == [f"2026-{month:02d}" for month in range(6, 13)]


def test_the_old_due_date_guard_would_have_created_may(test_db, actor_user):
    """Pins why the guard was not equivalent.

    May's due date is 15 June — still ahead of the 10 June onboarding — so the old
    `due_date < reference_date` check let it through. Only the liability range
    excludes it.
    """
    record = _client(test_db, actor_user, "123456781", vat_liable_from=date(2026, 6, 1))

    assert "2026-05" not in _vat_periods(test_db, record.id)


def test_a_late_onboarded_client_keeps_its_past_due_periods(test_db, actor_user):
    """The other direction. These are debts, not leftovers (D-26)."""
    record = _client(test_db, actor_user, "123456782")

    periods = _vat_periods(test_db, record.id)

    assert periods == [f"2026-{month:02d}" for month in range(1, 13)]
    assert "2026-01" in periods


def test_liability_end_stops_generation(test_db, actor_user):
    record = _client(
        test_db,
        actor_user,
        "123456783",
        vat_liable_from=date(2026, 2, 1),
        vat_liable_to=date(2026, 4, 30),
    )

    assert _vat_periods(test_db, record.id) == ["2026-02", "2026-03", "2026-04"]


def test_vat_and_advance_ranges_are_independent(test_db, actor_user):
    """The reason the range is per type and not one client-wide date."""
    record = _client(
        test_db,
        actor_user,
        "123456784",
        vat_liable_from=date(2026, 6, 1),
        advance_liable_from=date(2026, 9, 1),
    )

    assert _vat_periods(test_db, record.id) == [f"2026-{m:02d}" for m in range(6, 13)]
    assert _advance_periods(test_db, record.id) == [f"2026-{m:02d}" for m in range(9, 13)]


def test_no_range_configured_owes_everything(test_db, actor_user):
    """Unconfigured stays permissive — the range narrows, it never gates."""
    record = _client(test_db, actor_user, "123456785")

    assert len(_vat_periods(test_db, record.id)) == 12
    assert len(_advance_periods(test_db, record.id)) == 12


@pytest.mark.parametrize(
    ("start_field", "end_field"),
    [
        ("vat_liable_from", "vat_liable_to"),
        ("advance_liable_from", "advance_liable_to"),
        ("annual_liable_from", "annual_liable_to"),
    ],
)
def test_inverted_range_is_rejected_by_the_database(test_db, actor_user, start_field, end_field):
    """The request schemas reject this with a readable message, but they are not the
    only writer — this path reaches the repository directly, as the seed builders do.
    The CheckConstraint is what actually guarantees the invariant."""
    with pytest.raises(IntegrityError):
        _client(
            test_db,
            actor_user,
            "123456786",
            **{start_field: date(2026, 8, 1), end_field: date(2026, 3, 1)},
        )
    test_db.rollback()
