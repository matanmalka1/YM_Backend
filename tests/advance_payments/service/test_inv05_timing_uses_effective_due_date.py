"""INV-05 regression: timing_status and paid_late must use due_date_effective, not due_date."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.advance_payments.schemas.advance_payment import (
    AdvancePaymentOverviewRow,
    AdvancePaymentRow,
)


def _row(**kwargs) -> AdvancePaymentRow:
    defaults = dict(
        id=1,
        client_record_id=1,
        period="2026-01",
        period_months_count=1,
        due_date=date(2020, 2, 15),
        expected_amount=Decimal("100"),
        paid_amount=Decimal("0"),
        status=AdvancePaymentStatus.PENDING,
        calculated_amount=Decimal("100"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return AdvancePaymentRow(**defaults)


def _overview_row(**kwargs) -> AdvancePaymentOverviewRow:
    defaults = dict(
        id=1,
        client_record_id=1,
        business_name="Test",
        period="2026-01",
        period_months_count=1,
        due_date=date(2020, 2, 15),
        expected_amount=Decimal("100"),
        paid_amount=Decimal("0"),
        status=AdvancePaymentStatus.PENDING,
        calculated_amount=Decimal("100"),
    )
    defaults.update(kwargs)
    return AdvancePaymentOverviewRow(**defaults)


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

    def test_fallback_to_due_date_when_effective_is_none(self):
        """When due_date_effective is None, falls back to due_date (past → overdue)."""
        row = _row(due_date=date(2020, 2, 15), due_date_effective=None)
        assert row.timing_status == "overdue"

    def test_paid_payment_never_overdue(self):
        """Paid payments are always on_time regardless of dates."""
        row = _row(
            due_date=date(2020, 2, 15),
            due_date_effective=date(2020, 2, 15),
            status=AdvancePaymentStatus.PAID,
            paid_amount=Decimal("100"),
        )
        assert row.timing_status == "on_time"


class TestPaidLate:
    def test_paid_after_effective_date_is_late(self):
        """paid_at after due_date_effective → paid_late=True."""
        row = _row(
            due_date=date(2099, 2, 15),
            due_date_effective=date(2026, 2, 15),
            status=AdvancePaymentStatus.PAID,
            paid_amount=Decimal("100"),
            paid_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )
        assert row.paid_late is True

    def test_paid_before_effective_date_not_late(self):
        """paid_at before due_date_effective → paid_late=False."""
        row = _row(
            due_date=date(2020, 2, 15),
            due_date_effective=date(2026, 3, 1),
            status=AdvancePaymentStatus.PAID,
            paid_amount=Decimal("100"),
            paid_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
        assert row.paid_late is False

    def test_paid_after_due_date_but_on_time_vs_effective(self):
        """paid_at after legacy due_date but before due_date_effective → NOT late."""
        row = _row(
            due_date=date(2026, 2, 15),
            due_date_effective=date(2026, 3, 15),
            status=AdvancePaymentStatus.PAID,
            paid_amount=Decimal("100"),
            paid_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )
        assert row.paid_late is False

    def test_fallback_to_due_date_when_effective_none(self):
        """When due_date_effective is None, paid_late falls back to due_date."""
        row = _row(
            due_date=date(2026, 2, 15),
            due_date_effective=None,
            status=AdvancePaymentStatus.PAID,
            paid_amount=Decimal("100"),
            paid_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )
        assert row.paid_late is True


class TestOverviewTimingStatus:
    def test_overdue_when_effective_past(self):
        row = _overview_row(due_date=date(2020, 2, 15), due_date_effective=date(2020, 2, 15))
        assert row.timing_status == "overdue"

    def test_not_overdue_when_effective_future(self):
        """Legacy due_date is past but due_date_effective is future → on_time."""
        row = _overview_row(
            due_date=date(2020, 2, 15),
            due_date_effective=date(2099, 12, 31),
        )
        assert row.timing_status == "on_time"

    def test_fallback_when_effective_none(self):
        row = _overview_row(due_date=date(2020, 2, 15), due_date_effective=None)
        assert row.timing_status == "overdue"
