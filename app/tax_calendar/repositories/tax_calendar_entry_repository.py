from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import ObligationType
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry

EntryKey = tuple[str, int, str | None, int | None]


class TaxCalendarEntryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_periodic(
        self,
        obligation_type: ObligationType | str,
        period: str,
        period_months_count: int,
    ) -> TaxCalendarEntry | None:
        value = (
            obligation_type.value
            if isinstance(obligation_type, ObligationType)
            else obligation_type
        )
        return self.db.scalars(
            select(TaxCalendarEntry).where(
                TaxCalendarEntry.obligation_type == value,
                TaxCalendarEntry.period == period,
                TaxCalendarEntry.period_months_count == period_months_count,
            )
        ).one_or_none()

    def find_annual_id(self, tax_year: int) -> int | None:
        return self.db.scalar(
            select(TaxCalendarEntry.id).where(
                TaxCalendarEntry.obligation_type == ObligationType.ANNUAL_REPORT.value,
                TaxCalendarEntry.tax_year == tax_year,
            )
        )

    def count_in_year_range(self, start_year: int, end_year: int) -> int:
        return (
            self.db.scalar(
                select(func.count())
                .select_from(TaxCalendarEntry)
                .where(TaxCalendarEntry.tax_year.between(start_year, end_year))
            )
            or 0
        )

    def load_existing_keys(
        self,
        *,
        start_year: int,
        end_year: int,
        generated_obligation_values: set[str],
    ) -> set[EntryKey]:
        stmt = select(
            TaxCalendarEntry.obligation_type,
            TaxCalendarEntry.tax_year,
            TaxCalendarEntry.period,
            TaxCalendarEntry.period_months_count,
        ).where(
            TaxCalendarEntry.tax_year.between(start_year, end_year),
            TaxCalendarEntry.obligation_type.in_(generated_obligation_values),
        )
        return {
            (obligation_type, tax_year, period, period_months_count)
            for obligation_type, tax_year, period, period_months_count in self.db.execute(stmt)
        }

    def add(self, entry: TaxCalendarEntry) -> None:
        self.db.add(entry)

    def flush(self) -> None:
        self.db.flush()
