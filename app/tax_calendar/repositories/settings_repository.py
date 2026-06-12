from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.tax_calendar.models.deadline_rule import DeadlineRule
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry


class TaxCalendarSettingsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_rules(self) -> list[DeadlineRule]:
        stmt = select(DeadlineRule).order_by(
            DeadlineRule.rule_type.asc(), DeadlineRule.effective_from.asc()
        )
        return list(self.db.scalars(stmt).all())

    def list_entries(
        self,
        *,
        tax_year_after: int | None,
        tax_year_before: int | None,
    ) -> list[TaxCalendarEntry]:
        stmt = select(TaxCalendarEntry)
        if tax_year_after is not None:
            stmt = stmt.where(TaxCalendarEntry.tax_year >= tax_year_after)
        if tax_year_before is not None:
            stmt = stmt.where(TaxCalendarEntry.tax_year <= tax_year_before)
        stmt = stmt.order_by(
            TaxCalendarEntry.tax_year.asc(),
            TaxCalendarEntry.obligation_type.asc(),
            TaxCalendarEntry.period.asc().nulls_last(),
        )
        return list(self.db.scalars(stmt).all())

    def count_by_year_obligation_months(
        self,
        *,
        tax_year_after: int | None,
        tax_year_before: int | None,
    ) -> list[tuple[int, str, int | None, int]]:
        """Returns list of (tax_year, obligation_type, period_months_count, count)."""
        stmt = select(
            TaxCalendarEntry.tax_year,
            TaxCalendarEntry.obligation_type,
            TaxCalendarEntry.period_months_count,
            func.count(TaxCalendarEntry.id).label("entry_count"),
        )
        if tax_year_after is not None:
            stmt = stmt.where(TaxCalendarEntry.tax_year >= tax_year_after)
        if tax_year_before is not None:
            stmt = stmt.where(TaxCalendarEntry.tax_year <= tax_year_before)
        stmt = stmt.group_by(
            TaxCalendarEntry.tax_year,
            TaxCalendarEntry.obligation_type,
            TaxCalendarEntry.period_months_count,
        ).order_by(
            TaxCalendarEntry.tax_year.asc(),
            TaxCalendarEntry.obligation_type.asc(),
        )
        return list(self.db.execute(stmt).all())
