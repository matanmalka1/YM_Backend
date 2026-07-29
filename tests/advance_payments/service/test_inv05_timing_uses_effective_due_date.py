"""INV-05 regression: timing_status must use due_date_effective, not due_date.

The paid-lateness half of this invariant moved in W3: ``paid_late`` was a
computed row field and is now the stored ``closed_late`` fact, written once at
the close. Its effective-date precedence is asserted in
tests/advance_payments/api/test_advance_payment_status_transitions.py.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.advance_payments.schemas.advance_payment import AdvancePaymentRow
from app.common.enums import ObligationStatus


def _row(**kwargs) -> AdvancePaymentRow:
    defaults = dict(
        id=1,
        client_record_id=1,
        period="2026-01",
        period_months_count=1,
        due_date=date(2020, 2, 15),
        expected_amount=Decimal("100"),
        paid_amount=Decimal("0"),
        status=ObligationStatus.AWAITING_INPUT,
        calculated_amount=Decimal("100"),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    defaults.update(kwargs)
    return AdvancePaymentRow(**defaults)


class TestTimingStatus:
    def test_overdue_when_effective_past_today(self):
        """Unpaid + due_date_effective in the past → overdue."""
        row = _row(due_date=date(2020, 2, 15), due_date_effective=date(2020, 2, 15))
        assert row.timing_status == "overdue"

    def test_not_overdue_when_effective_in_future(self):
        """Unpaid + due_date is past but due_date_effective is future → NOT overdue."""
        row = _row(
            due_date=date(2020, 2, 15),
            due_date_effective=date(2099, 12, 31),
        )
        assert row.timing_status == "on_time"

    def test_paid_payment_never_overdue(self):
        """Paid payments are always on_time regardless of dates."""
        row = _row(
            due_date=date(2020, 2, 15),
            due_date_effective=date(2020, 2, 15),
            status=ObligationStatus.SUBMITTED,
            paid_amount=Decimal("100"),
        )
        assert row.timing_status == "on_time"
