"""Regression tests: advance payment due_date comes from TaxCalendarEntry, not build_due_date()."""

from datetime import date

from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.common.enums import DeadlineRuleType, ObligationType
from tests.helpers.tax_calendar_links import advance_client, make_entry


def generate_annual_schedule(
    client_record_id, year, db, period_months_count=None, reference_date=None
):
    return AdvancePaymentService(db).generate_annual_schedule(
        client_record_id,
        year,
        period_months_count=period_months_count,
        reference_date=reference_date,
    )


def test_advance_payment_due_date_from_entry_not_hardcoded_15(test_db):
    """Regression: when TaxCalendarEntry.due_date=2026-02-16, payment must store 2026-02-16, not 2026-02-15."""
    entry = make_entry(
        test_db,
        obligation_type=ObligationType.ADVANCE_PAYMENT,
        rule_type=DeadlineRuleType.ADVANCE_MONTHLY,
        period="2026-01",
        months=1,
        tax_year=2026,
    )
    # Simulate a holiday shift: tax authority moves deadline from 15th to 16th.
    entry.due_date = date(2026, 2, 16)
    test_db.flush()

    client = advance_client(test_db)
    created, skipped = generate_annual_schedule(
        client.id, 2026, test_db, reference_date=date(2025, 12, 31)
    )

    jan = next(p for p in created if p.period == "2026-01")

    assert jan.due_date == date(2026, 2, 16), (
        f"expected 2026-02-16 from TaxCalendarEntry, got {jan.due_date} (hardcoded 15th is wrong)"
    )
    assert jan.due_date_original == date(2026, 2, 16)
    assert jan.due_date_effective == date(2026, 2, 16)
    assert jan.tax_calendar_entry_id == entry.id


def test_create_payment_directly_uses_entry_due_date(test_db):
    """create_payment_for_client ignores caller-supplied due_date, uses TaxCalendarEntry.due_date."""
    entry = make_entry(
        test_db,
        obligation_type=ObligationType.ADVANCE_PAYMENT,
        rule_type=DeadlineRuleType.ADVANCE_MONTHLY,
        period="2026-03",
        months=1,
        tax_year=2026,
    )
    entry.due_date = date(2026, 4, 16)
    test_db.flush()

    client = advance_client(test_db)
    service = AdvancePaymentService(test_db)
    payment = service.create_payment_for_client(
        client_record_id=client.id,
        period="2026-03",
        period_months_count=1,
    )

    assert payment.due_date == date(2026, 4, 16)
    assert payment.due_date_original == date(2026, 4, 16)
    assert payment.due_date_effective == date(2026, 4, 16)
