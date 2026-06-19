from datetime import date

from app.annual_reports.services.annual_report_season_service import (
    get_active_annual_report_tax_year,
    get_filing_season_year,
)


def test_active_annual_report_tax_year_uses_previous_calendar_year():
    assert get_active_annual_report_tax_year(date(2026, 4, 30)) == 2025


def test_filing_season_year_is_display_metadata():
    assert get_filing_season_year(2025) == 2026
