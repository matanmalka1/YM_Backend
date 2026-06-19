from decimal import ROUND_HALF_UP, Decimal

from app.annual_reports.schemas.annual_report_responses import (
    DefaultTaxYearResponse,
    SeasonSummaryResponse,
)
from app.utils.time_utils import israel_today

from .annual_report_base import AnnualReportBaseService


def get_active_annual_report_tax_year(today=None) -> int:
    filing_date = today or israel_today()
    return filing_date.year - 1


def get_filing_season_year(tax_year: int) -> int:
    return tax_year + 1


class AnnualReportSeasonService(AnnualReportBaseService):
    def get_default_tax_year_response(self) -> DefaultTaxYearResponse:
        active_report = self.repo.get_default_tax_year_candidate()
        if active_report:
            return DefaultTaxYearResponse(tax_year=active_report.tax_year)
        tax_year = self.repo.get_latest_tax_year() or self._fallback_tax_year()
        return DefaultTaxYearResponse(tax_year=tax_year)

    def _fallback_tax_year(self) -> int:
        return israel_today().year - 1

    def get_season_summary_response(self, tax_year: int) -> SeasonSummaryResponse:
        summary = self.repo.get_season_summary(tax_year)
        overdue_count = len(self.repo.list_overdue(tax_year=tax_year))
        total = summary.get("total", 0)
        done = summary.get("submitted", 0) + summary.get("closed", 0)
        completion_rate = (
            (Decimal(done) / Decimal(total) * Decimal("100")).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
            if total > 0
            else Decimal("0")
        )
        return SeasonSummaryResponse(
            tax_year=tax_year,
            filing_season_year=get_filing_season_year(tax_year),
            total=total,
            not_started=summary.get("not_started", 0),
            collecting_docs=summary.get("collecting_docs", 0),
            in_preparation=summary.get("in_preparation", 0),
            pending_client=summary.get("pending_client", 0),
            submitted=summary.get("submitted", 0),
            closed=summary.get("closed", 0),
            completion_rate=completion_rate,
            overdue_count=overdue_count,
        )


__all__ = [
    "AnnualReportSeasonService",
    "get_active_annual_report_tax_year",
    "get_filing_season_year",
]
