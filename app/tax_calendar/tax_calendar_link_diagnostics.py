from sqlalchemy.orm import Session

from app.tax_calendar.repositories.tax_calendar_link_diagnostics_repository import (
    TaxCalendarLinkDiagnosticsRepository,
)


def find_active_null_tax_calendar_links(db: Session) -> dict[str, dict[str, object]]:
    return TaxCalendarLinkDiagnosticsRepository(db).find_null_calendar_links()
