"""Shared period/deadline helpers used across advance_payments, binders, and dashboard.

``period`` is always the ``YYYY-MM`` string of the first month in a reporting period.
The parsers here are the only implementation: they validate the shape rather than
trusting the caller, because a malformed period used to surface as a ``ValueError``
or an ``IndexError`` from whichever call site sliced the string by hand.
"""

import re
from datetime import date

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError

PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

HEBREW_MONTHS = (
    "ינואר",
    "פברואר",
    "מרץ",
    "אפריל",
    "מאי",
    "יוני",
    "יולי",
    "אוגוסט",
    "ספטמבר",
    "אוקטובר",
    "נובמבר",
    "דצמבר",
)


def parse_period(period: str) -> tuple[int, int]:
    """Split a ``YYYY-MM`` period into ``(year, month)``, rejecting anything else."""
    if not isinstance(period, str) or not PERIOD_PATTERN.match(period):
        raise AppError("תקופת המס אינה תקינה", ErrorCode.TAX_CALENDAR_INVALID_PERIOD)
    return int(period[:4]), int(period[5:7])


def parse_period_year(period: str) -> int:
    return parse_period(period)[0]


def parse_period_month(period: str) -> int:
    return parse_period(period)[1]


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    month_index = year * 12 + month - 1 + offset
    return month_index // 12, month_index % 12 + 1


def _period_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def latest_monthly_period(reference_date: date) -> tuple[str, str]:
    """The most recent closed monthly period, as ``(period, label)``."""
    year, month = _shift_month(reference_date.year, reference_date.month, -1)
    return _period_key(year, month), f"{HEBREW_MONTHS[month - 1]} {year}"


def latest_bimonthly_period(reference_date: date) -> tuple[str, str]:
    """The most recent closed bi-monthly period, as ``(period, label)``.

    VAT and advance payments ask this the same way — the frequencies are configured
    independently per client, but the calendar arithmetic is one rule.
    """
    year, end_month = _shift_month(reference_date.year, reference_date.month, -1)
    if end_month % 2:
        year, end_month = _shift_month(year, end_month, -1)
    start_year, start_month = _shift_month(year, end_month, -1)
    label = f"{HEBREW_MONTHS[start_month - 1]}-{HEBREW_MONTHS[end_month - 1]} {year}"
    if start_year != year:
        label = (
            f"{HEBREW_MONTHS[start_month - 1]} {start_year}-{HEBREW_MONTHS[end_month - 1]} {year}"
        )
    return _period_key(start_year, start_month), label
