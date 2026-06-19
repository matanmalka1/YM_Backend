"""TaxCalendarEntry lookup helpers for transitional FK wiring."""

from sqlalchemy.orm import Session

from app.common.enums import ObligationType
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry
from app.tax_calendar.repositories.tax_calendar_entry_repository import TaxCalendarEntryRepository


def find_periodic_entry_id(
    db: Session,
    obligation_type: ObligationType | str,
    period: str,
    period_months_count: int,
) -> int | None:
    entry = find_periodic_entry(db, obligation_type, period, period_months_count)
    return entry.id if entry else None


def find_periodic_entry(
    db: Session,
    obligation_type: ObligationType | str,
    period: str,
    period_months_count: int,
) -> TaxCalendarEntry | None:
    return TaxCalendarEntryRepository(db).find_periodic(
        obligation_type, period, period_months_count
    )


def find_annual_entry_id(db: Session, tax_year: int) -> int | None:
    return TaxCalendarEntryRepository(db).find_annual_id(tax_year)
