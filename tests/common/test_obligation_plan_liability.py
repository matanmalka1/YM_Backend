"""The obligation plan is the single answer to "is this period owed?".

A liability range narrows it per obligation type. The rule is **intersection**, not
containment: a period the client was liable for on any of its days is owed, because
the authority does not prorate a return.
"""

from datetime import date

import pytest

from app.common.enums import AdvancePaymentFrequency, EntityType, VatType
from app.common.obligation_plan import (
    advance_payment_obligation_plan,
    is_period_owed,
    vat_obligation_plan,
)


def _periods(plans):
    return [p.period for p in plans]


class TestUnboundedIsUnchanged:
    """No range configured means every period the frequency implies."""

    def test_monthly_vat_is_twelve_periods(self):
        assert len(vat_obligation_plan(VatType.MONTHLY, 2026)) == 12

    def test_bimonthly_vat_is_six_odd_start_periods(self):
        plans = vat_obligation_plan(VatType.BIMONTHLY, 2026)
        assert _periods(plans) == [
            "2026-01",
            "2026-03",
            "2026-05",
            "2026-07",
            "2026-09",
            "2026-11",
        ]

    def test_exempt_owes_nothing(self):
        assert vat_obligation_plan(VatType.EXEMPT, 2026) == []
        assert vat_obligation_plan(None, 2026) == []

    def test_employee_owes_no_advances(self):
        assert (
            advance_payment_obligation_plan(
                frequency=AdvancePaymentFrequency.MONTHLY,
                year=2026,
                entity_type=EntityType.EMPLOYEE,
            )
            == []
        )


class TestLiableFrom:
    def test_monthly_vat_starts_at_the_month_of_liability(self):
        """O-7, stated directly: a client liable from June owes no May period."""
        plans = vat_obligation_plan(VatType.MONTHLY, 2026, liable_from=date(2026, 6, 1))
        assert _periods(plans) == [
            "2026-06",
            "2026-07",
            "2026-08",
            "2026-09",
            "2026-10",
            "2026-11",
            "2026-12",
        ]

    def test_liability_mid_month_still_owes_that_month(self):
        plans = vat_obligation_plan(VatType.MONTHLY, 2026, liable_from=date(2026, 6, 20))
        assert plans[0].period == "2026-06"

    def test_bimonthly_period_is_owed_when_liability_starts_inside_it(self):
        """The load-bearing case: May–June, liable from 20 June → still owed.

        Containment would drop it and lose a real obligation.
        """
        plans = vat_obligation_plan(VatType.BIMONTHLY, 2026, liable_from=date(2026, 6, 20))
        assert _periods(plans) == ["2026-05", "2026-07", "2026-09", "2026-11"]

    def test_liability_starting_after_the_year_owes_nothing(self):
        assert vat_obligation_plan(VatType.MONTHLY, 2026, liable_from=date(2027, 1, 1)) == []

    def test_liability_starting_before_the_year_owes_everything(self):
        assert len(vat_obligation_plan(VatType.MONTHLY, 2026, liable_from=date(2020, 1, 1))) == 12


class TestLiableTo:
    def test_monthly_vat_stops_after_the_month_liability_ends(self):
        plans = vat_obligation_plan(VatType.MONTHLY, 2026, liable_to=date(2026, 3, 31))
        assert _periods(plans) == ["2026-01", "2026-02", "2026-03"]

    def test_liability_ending_mid_month_still_owes_that_month(self):
        plans = vat_obligation_plan(VatType.MONTHLY, 2026, liable_to=date(2026, 3, 2))
        assert _periods(plans) == ["2026-01", "2026-02", "2026-03"]

    def test_liability_ending_before_the_year_owes_nothing(self):
        assert vat_obligation_plan(VatType.MONTHLY, 2026, liable_to=date(2025, 12, 31)) == []


class TestBothEnds:
    def test_a_closed_range_owes_only_the_months_inside_it(self):
        plans = vat_obligation_plan(
            VatType.MONTHLY,
            2026,
            liable_from=date(2026, 4, 1),
            liable_to=date(2026, 7, 31),
        )
        assert _periods(plans) == ["2026-04", "2026-05", "2026-06", "2026-07"]

    def test_advance_payments_clip_independently_of_vat(self):
        """The reason ranges are per type: they move independently."""
        plans = advance_payment_obligation_plan(
            frequency=AdvancePaymentFrequency.MONTHLY,
            year=2026,
            liable_from=date(2026, 9, 1),
        )
        assert _periods(plans) == ["2026-09", "2026-10", "2026-11", "2026-12"]


class TestIsPeriodOwed:
    @pytest.mark.parametrize(
        ("start_month", "months", "liable_from", "liable_to", "expected"),
        [
            # period fully before the range
            (1, 1, date(2026, 2, 1), None, False),
            # period fully after the range
            (6, 1, None, date(2026, 5, 31), False),
            # liability begins on the period's last day
            (3, 1, date(2026, 3, 31), None, True),
            # liability ends on the period's first day
            (3, 1, None, date(2026, 3, 1), True),
            # a bi-monthly span that ends in a later month
            (11, 2, date(2026, 12, 1), None, True),
            # unbounded both ways
            (7, 1, None, None, True),
        ],
    )
    def test_boundaries(self, start_month, months, liable_from, liable_to, expected):
        assert (
            is_period_owed(
                2026,
                start_month,
                months,
                liable_from=liable_from,
                liable_to=liable_to,
            )
            is expected
        )
