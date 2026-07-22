from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.enums import ObligationType
from app.tax_calendar.integrations.tax_rules_registry import missing_registry_years
from app.tax_calendar.models.tax_calendar_deadline_rule import DeadlineRule
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry
from app.tax_calendar.repositories.tax_calendar_settings_repository import (
    TaxCalendarSettingsRepository,
)
from app.tax_calendar.services.tax_calendar_bootstrap_service import bootstrap_tax_calendar

# (obligation_type, period_months_count) → expected count per year
# None for period_months_count = annual (no period)
_EXPECTED_BREAKDOWN: dict[tuple[ObligationType, int | None], int] = {
    (ObligationType.VAT, 1): 12,
    (ObligationType.VAT, 2): 6,
    (ObligationType.ADVANCE_PAYMENT, 1): 12,
    (ObligationType.ADVANCE_PAYMENT, 2): 6,
    (ObligationType.ANNUAL_REPORT, None): 1,
}


def list_rules(db: Session) -> list[DeadlineRule]:
    return TaxCalendarSettingsRepository(db).list_rules()


def list_entries(
    db: Session,
    *,
    tax_year_after: int | None,
    tax_year_before: int | None,
) -> list[TaxCalendarEntry]:
    return TaxCalendarSettingsRepository(db).list_entries(
        tax_year_after=tax_year_after, tax_year_before=tax_year_before
    )


def get_summary(
    db: Session,
    *,
    tax_year_after: int | None,
    tax_year_before: int | None,
) -> dict:
    repo = TaxCalendarSettingsRepository(db)
    rows = repo.count_by_year_obligation_months(
        tax_year_after=tax_year_after, tax_year_before=tax_year_before
    )

    # Build per-year breakdown keyed by "{obligation_type}_{months_count or 'annual'}"
    per_year: dict[int, dict[str, int]] = {}
    actual: dict[tuple[int, ObligationType, int | None], int] = {}
    for tax_year, obligation_type_val, period_months_count, count in rows:
        obligation = ObligationType(obligation_type_val)
        label = _summary_label(obligation, period_months_count)
        per_year.setdefault(tax_year, {})[label] = count
        actual[(tax_year, obligation, period_months_count)] = count

    warnings: list[dict[str, object]] = []
    # Check all years in range, not just those with entries
    if tax_year_after is not None and tax_year_before is not None:
        years_to_check = range(tax_year_after, tax_year_before + 1)
    else:
        years_to_check = sorted(per_year.keys())
    for year in years_to_check:
        for (obtype, months), expected_count in _EXPECTED_BREAKDOWN.items():
            found = actual.get((year, obtype, months), 0)
            if found != expected_count:
                label = _summary_label(obtype, months)
                warnings.append(
                    {
                        "code": "count_mismatch",
                        "year": year,
                        "obligation_type": label,
                        "expected": expected_count,
                        "found": found,
                    }
                )

    # Warn for years using DeadlineRule fallback (no official registry calendar)
    if tax_year_after is not None and tax_year_before is not None:
        for year in missing_registry_years(tax_year_after, tax_year_before):
            warnings.append({"code": "registry_data_missing", "year": year})
    elif per_year:
        all_years = sorted(per_year.keys())
        for year in missing_registry_years(all_years[0], all_years[-1]):
            if year in per_year:
                warnings.append({"code": "registry_data_missing", "year": year})

    total_entries = sum(c for year_data in per_year.values() for c in year_data.values())

    return {
        "tax_year_after": tax_year_after,
        "tax_year_before": tax_year_before,
        "total_entries": total_entries,
        "per_year": per_year,
        "warnings": warnings,
    }


def bootstrap_calendar(
    db: Session,
    *,
    tax_year_after: int,
    tax_year_before: int,
) -> dict[str, object]:
    result = bootstrap_tax_calendar(db, start_year=tax_year_after, end_year=tax_year_before)
    return {
        "tax_year_after": result["start_year"],
        "tax_year_before": result["end_year"],
        "rules_created": result["rules_created"],
        "rules_skipped": result["rules_skipped"],
        "rules_by_type": result["rules_by_type"],
        "entries_created": result["entries_created"],
        "entries_skipped": result["entries_skipped"],
        "total_entries_for_range": result["total_entries_for_range"],
        "warnings": result["warnings"],
    }


def _summary_label(obligation: ObligationType, months: int | None) -> str:
    if months is None:
        return f"{obligation.value}_annual"
    return f"{obligation.value}_{months}m"
