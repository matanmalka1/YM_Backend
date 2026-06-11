"""Local/dev bootstrap for tax calendar regulatory defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.common.enums import DeadlineRuleType
from app.tax_calendar.integrations.tax_rules_registry import (
    registry_periodic_calendar_available,
)
from app.tax_calendar.models.deadline_rule import DeadlineRule
from app.tax_calendar.repositories.deadline_rule_repository import DeadlineRuleRepository
from app.tax_calendar.repositories.entry_repository import TaxCalendarEntryRepository
from app.tax_calendar.services.tax_calendar_entry_service import generate_for_year_range
from app.utils.time_utils import israel_today

DEFAULT_EFFECTIVE_FROM = date(2023, 1, 1)
EXPECTED_ENTRIES_PER_YEAR = 37  # 12 vat_monthly + 6 vat_bimonthly + 12 advance_monthly + 6 advance_bimonthly + 1 annual_report


@dataclass(frozen=True)
class DefaultDeadlineRule:
    rule_type: DeadlineRuleType
    due_day_of_month: int
    offset_months: int


DEFAULT_DEADLINE_RULES: tuple[DefaultDeadlineRule, ...] = (
    DefaultDeadlineRule(DeadlineRuleType.VAT_MONTHLY, 15, 1),
    DefaultDeadlineRule(DeadlineRuleType.VAT_BIMONTHLY, 15, 2),
    DefaultDeadlineRule(DeadlineRuleType.ADVANCE_MONTHLY, 15, 1),
    DefaultDeadlineRule(DeadlineRuleType.ADVANCE_BIMONTHLY, 15, 2),
    DefaultDeadlineRule(DeadlineRuleType.ANNUAL_REPORT, 31, 4),
)


@dataclass(frozen=True)
class SeedRulesResult:
    created: int
    skipped: int
    by_rule_type: dict[str, str] = field(default_factory=dict)


def seed_default_deadline_rules(db: Session) -> SeedRulesResult:
    """Create missing open-ended default rules. Idempotent."""
    repo = DeadlineRuleRepository(db)
    created = 0
    skipped = 0
    by_rule_type: dict[str, str] = {}
    for default in DEFAULT_DEADLINE_RULES:
        key = default.rule_type.value
        if repo.has_open_ended_rule(default.rule_type):
            skipped += 1
            by_rule_type[key] = "skipped"
            continue
        repo.add(
            DeadlineRule(
                rule_type=default.rule_type,
                due_day_of_month=default.due_day_of_month,
                offset_months=default.offset_months,
                effective_from=DEFAULT_EFFECTIVE_FROM,
                effective_to=None,
                description="Default local/dev tax calendar bootstrap rule",
            )
        )
        created += 1
        by_rule_type[key] = "created"
    repo.flush()
    return SeedRulesResult(created=created, skipped=skipped, by_rule_type=by_rule_type)


def default_year_range(today: date | None = None) -> tuple[int, int]:
    current_year = (today or israel_today()).year
    next_year = current_year + 1
    if registry_periodic_calendar_available(next_year):
        return current_year, next_year
    return current_year, current_year


def bootstrap_tax_calendar(
    db: Session,
    *,
    start_year: int | None = None,
    end_year: int | None = None,
    today: date | None = None,
) -> dict[str, object]:
    """Seed default rules and generate TaxCalendarEntry rows for a year range."""
    default_start, default_end = default_year_range(today)
    resolved_start = start_year if start_year is not None else default_start
    resolved_end = end_year if end_year is not None else default_end

    rules_result = seed_default_deadline_rules(db)
    entries_result = generate_for_year_range(
        db,
        start_year=resolved_start,
        end_year=resolved_end,
    )

    num_years = resolved_end - resolved_start + 1
    total_in_range = TaxCalendarEntryRepository(db).count_in_year_range(
        resolved_start, resolved_end
    )

    warnings: list[str] = []
    expected = EXPECTED_ENTRIES_PER_YEAR * num_years
    if total_in_range != expected:
        warnings.append(
            f"Expected {expected} entries for {resolved_start}–{resolved_end} "
            f"({EXPECTED_ENTRIES_PER_YEAR}/year), found {total_in_range}."
        )

    return {
        "start_year": resolved_start,
        "end_year": resolved_end,
        "rules_created": rules_result.created,
        "rules_skipped": rules_result.skipped,
        "rules_by_type": rules_result.by_rule_type,
        "entries_created": entries_result.entries_created,
        "entries_skipped": entries_result.entries_skipped,
        "total_entries_for_range": total_in_range,
        "warnings": warnings,
    }
