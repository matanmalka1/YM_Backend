"""What a client owes, per obligation type and year.

This module is the single answer to "is this period owed?". Nothing else decides
it — generation creates what the plan lists, and reconciliation classifies existing
rows against the same list.

Two things narrow a plan: the client's configured frequency, and the client's
liability range for that obligation type. The range is per type because they move
independently — an entity can register for VAT in June, receive an ITA advance rate
in September, and still owe a full-year annual report for the same year.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date

from app.common.enums import AdvancePaymentFrequency, EntityType, VatType


@dataclass(frozen=True, slots=True)
class PeriodicObligationPlan:
    period: str
    period_months_count: int


def _period_span(year: int, start_month: int, months_count: int) -> tuple[date, date]:
    """The first and last calendar day the period covers."""
    end_month_index = start_month - 1 + months_count - 1
    end_year = year + end_month_index // 12
    end_month = end_month_index % 12 + 1
    return (
        date(year, start_month, 1),
        date(end_year, end_month, monthrange(end_year, end_month)[1]),
    )


def is_period_owed(
    year: int,
    start_month: int,
    months_count: int,
    *,
    liable_from: date | None,
    liable_to: date | None,
) -> bool:
    """Whether a liability range covers any part of a reporting period.

    Intersection, not containment: a bi-monthly period covering May–June on a
    client liable from 20 June **is** owed. Partial liability inside a period
    still creates the obligation — the authority does not prorate a return.

    NULL is unbounded on that side, so a client with no range configured owes
    every period the frequency implies.
    """
    period_start, period_end = _period_span(year, start_month, months_count)
    if liable_from is not None and period_end < liable_from:
        return False
    if liable_to is not None and period_start > liable_to:
        return False
    return True


def vat_obligation_plan(
    vat_type: VatType | None,
    year: int,
    *,
    liable_from: date | None = None,
    liable_to: date | None = None,
) -> list[PeriodicObligationPlan]:
    if vat_type in (VatType.EXEMPT, None):
        return []

    if vat_type == VatType.MONTHLY:
        period_starts = list(range(1, 13))
        period_months_count = 1
    else:
        period_starts = list(range(1, 12, 2))
        period_months_count = 2

    return [
        PeriodicObligationPlan(
            period=f"{year}-{month:02d}",
            period_months_count=period_months_count,
        )
        for month in period_starts
        if is_period_owed(
            year,
            month,
            period_months_count,
            liable_from=liable_from,
            liable_to=liable_to,
        )
    ]


def advance_payment_obligation_plan(
    *,
    frequency: AdvancePaymentFrequency,
    year: int,
    entity_type: EntityType | None = None,
    liable_from: date | None = None,
    liable_to: date | None = None,
) -> list[PeriodicObligationPlan]:
    if entity_type == EntityType.EMPLOYEE:
        return []

    if frequency == AdvancePaymentFrequency.BIMONTHLY:
        period_starts = [1, 3, 5, 7, 9, 11]
        period_months_count = 2
    else:
        period_starts = list(range(1, 13))
        period_months_count = 1

    return [
        PeriodicObligationPlan(
            period=f"{year}-{month:02d}",
            period_months_count=period_months_count,
        )
        for month in period_starts
        if is_period_owed(
            year,
            month,
            period_months_count,
            liable_from=liable_from,
            liable_to=liable_to,
        )
    ]
