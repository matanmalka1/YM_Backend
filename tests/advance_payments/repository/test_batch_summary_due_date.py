"""Tests: batch_summary_by_month returns due_date from TaxCalendarEntry and groups correctly."""

from datetime import date

from app.advance_payments.repositories.advance_payment_batch_repository import (
    AdvancePaymentBatchRepository,
)
from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.common.enums import AdvancePaymentFrequency, DeadlineRuleType, ObligationType
from tests.helpers.tax_calendar_links import make_entry


def _payment(db, client_id, period, period_months_count, entry):
    repo = AdvancePaymentRepository(db)
    return repo.create(
        client_record_id=client_id,
        period=period,
        period_months_count=period_months_count,
        due_date=entry.due_date,
        tax_calendar_entry_id=entry.id,
    )


def test_batch_summary_returns_due_date_from_tax_calendar_entry(
    test_db, create_client_with_business
):
    """due_date in batch summary must come from TaxCalendarEntry, not hardcoded 15."""
    entry = make_entry(
        test_db,
        obligation_type=ObligationType.ADVANCE_PAYMENT,
        rule_type=DeadlineRuleType.ADVANCE_MONTHLY,
        period="2026-01",
        months=1,
        tax_year=2026,
    )
    entry.due_date = date(2026, 2, 16)
    test_db.flush()

    client, _business = create_client_with_business(commit=False)
    _payment(test_db, client.id, "2026-01", 1, entry)
    test_db.flush()

    rows = AdvancePaymentBatchRepository(test_db).batch_summary_by_month(
        2026, reference_date=date(2026, 2, 1)
    )

    jan = next((r for r in rows if int(r.month) == 1), None)
    assert jan is not None
    assert jan.due_date == date(2026, 2, 16), (
        f"expected 2026-02-16 from TaxCalendarEntry, got {jan.due_date}"
    )
    assert jan.due_this_month_count == 1


def test_batch_summary_monthly_and_bimonthly_same_start_month_are_separate_rows(
    test_db,
    create_client_with_business,
):
    """Monthly period '2026-01' and bimonthly period '2026-01' must NOT be merged."""
    entry_monthly = make_entry(
        test_db,
        obligation_type=ObligationType.ADVANCE_PAYMENT,
        rule_type=DeadlineRuleType.ADVANCE_MONTHLY,
        period="2026-01",
        months=1,
        tax_year=2026,
    )
    entry_bimonthly = make_entry(
        test_db,
        obligation_type=ObligationType.ADVANCE_PAYMENT,
        rule_type=DeadlineRuleType.ADVANCE_BIMONTHLY,
        period="2026-01",
        months=2,
        tax_year=2026,
    )
    entry_monthly.due_date = date(2026, 2, 15)
    entry_bimonthly.due_date = date(2026, 3, 15)
    test_db.flush()

    client_m, _business_m = create_client_with_business(
        commit=False, advance_payment_frequency=AdvancePaymentFrequency.MONTHLY
    )
    client_b, _business_b = create_client_with_business(
        commit=False, advance_payment_frequency=AdvancePaymentFrequency.BIMONTHLY
    )
    _payment(test_db, client_m.id, "2026-01", 1, entry_monthly)
    _payment(test_db, client_b.id, "2026-01", 2, entry_bimonthly)
    test_db.flush()

    rows = AdvancePaymentBatchRepository(test_db).batch_summary_by_month(
        2026, reference_date=date(2026, 2, 1)
    )
    jan_rows = [r for r in rows if int(r.month) == 1]

    assert len(jan_rows) == 2, (
        f"expected 2 separate rows for month=1 (monthly vs bimonthly), got {len(jan_rows)}"
    )
    period_counts = {int(r.period_months_count) for r in jan_rows}
    assert period_counts == {1, 2}


def test_batch_summary_due_date_is_none_when_no_payments(test_db):
    """If no payments exist for the year, result is empty (no crash, no null due_date rows)."""
    rows = AdvancePaymentBatchRepository(test_db).batch_summary_by_month(
        2099, reference_date=date(2099, 1, 1)
    )
    assert rows == []
