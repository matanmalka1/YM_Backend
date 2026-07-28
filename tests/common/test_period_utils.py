from datetime import date

import pytest

from app.common.period_utils import (
    latest_bimonthly_period,
    latest_monthly_period,
    parse_period,
    parse_period_month,
    parse_period_year,
)
from app.core.exceptions import AppError


def test_monthly_period_is_previous_month():
    assert latest_monthly_period(date(2026, 4, 10)) == ("2026-03", "מרץ 2026")


def test_bimonthly_period_is_reportable_pair_not_current_pair():
    assert latest_bimonthly_period(date(2026, 4, 10)) == (
        "2026-01",
        "ינואר-פברואר 2026",
    )


def test_bimonthly_period_uses_pair_that_just_closed():
    assert latest_bimonthly_period(date(2026, 5, 10)) == (
        "2026-03",
        "מרץ-אפריל 2026",
    )


def test_bimonthly_label_spans_the_year_boundary():
    assert latest_bimonthly_period(date(2026, 2, 10)) == (
        "2025-11",
        "נובמבר-דצמבר 2025",
    )


class TestPeriodParsing:
    def test_parses_year_and_month(self):
        assert parse_period("2026-03") == (2026, 3)
        assert parse_period_year("2026-03") == 2026
        assert parse_period_month("2026-03") == 3

    @pytest.mark.parametrize(
        "period",
        ["2026-13", "2026-00", "2026-3", "26-03", "2026/03", "2026-03-01", "", "not-a-period"],
    )
    def test_rejects_malformed_period(self, period):
        # The hand-rolled int(period[:4]) call sites this replaced raised ValueError
        # or IndexError, or silently accepted a month of 13.
        with pytest.raises(AppError) as exc_info:
            parse_period(period)
        assert exc_info.value.code == "TAX_CALENDAR.INVALID_PERIOD"

    def test_rejects_non_string(self):
        with pytest.raises(AppError):
            parse_period(202603)  # type: ignore[arg-type]
