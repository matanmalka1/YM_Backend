"""TaxCalendarEntry generation — calendar population.

Populates regulatory calendar entries shared across all clients. Idempotent:
re-running for the same year is a no-op. Does NOT modify business objects.

Due-date computation (priority order):
1. Official effective date from tax_rules_config registry
   (column: effective_vat_periodic_and_income_tax_advances).
   Covers VAT + advance payment periodic obligations, including holiday shifts.
   This is the STATUTORY effective date (15th shifted for holidays/weekends).
   It does NOT include the +4-day online filing extension — that is applied by
   the VAT serializer layer for online-submission clients only.
2. DeadlineRule base: (period start + offset_months) on due_day_of_month.
   Used when registry has no data for the year (e.g. future/past years).
- Annual entry:   due_date = (tax_year + 1 + offset_months) on due_day_of_month.
- Per-client overrides (extended/custom annual deadlines) live on AnnualReport.
- Registry lookup is restricted to VAT and advance-payment rule types only.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.audit.audit_constants import ACTION_TAX_CALENDAR_GENERATED, ENTITY_TAX_CALENDAR
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.common.enums import DeadlineRuleType, ObligationType
from app.tax_calendar.integrations.tax_rules_registry import get_registry_due_date
from app.tax_calendar.models.tax_calendar_deadline_rule import DeadlineRule
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry
from app.tax_calendar.repositories.tax_calendar_deadline_rule_repository import (
    DeadlineRuleRepository,
)
from app.tax_calendar.repositories.tax_calendar_entry_repository import (
    EntryKey,
    TaxCalendarEntryRepository,
)


class MissingDeadlineRuleError(LookupError):
    """No active DeadlineRule covers the requested rule_type/year."""


@dataclass(frozen=True)
class YearGenerationResult:
    created: int
    skipped: int


@dataclass(frozen=True)
class YearRangeResult:
    entries_created: int
    entries_skipped: int


_PERIODIC_PLAN: list[tuple[ObligationType, DeadlineRuleType, list[int], int]] = [
    (ObligationType.VAT, DeadlineRuleType.VAT_MONTHLY, list(range(1, 13)), 1),
    (ObligationType.VAT, DeadlineRuleType.VAT_BIMONTHLY, [1, 3, 5, 7, 9, 11], 2),
    (
        ObligationType.ADVANCE_PAYMENT,
        DeadlineRuleType.ADVANCE_MONTHLY,
        list(range(1, 13)),
        1,
    ),
    (
        ObligationType.ADVANCE_PAYMENT,
        DeadlineRuleType.ADVANCE_BIMONTHLY,
        [1, 3, 5, 7, 9, 11],
        2,
    ),
]

_GENERATED_OBLIGATION_VALUES = {
    ObligationType.VAT.value,
    ObligationType.ADVANCE_PAYMENT.value,
    ObligationType.ANNUAL_REPORT.value,
}


def _shift_month(year: int, month: int, offset_months: int) -> tuple[int, int]:
    total = (month - 1) + offset_months
    return year + total // 12, (total % 12) + 1


def _clamp_day(year: int, month: int, day: int) -> int:
    return min(day, calendar.monthrange(year, month)[1])


def periodic_due_date(rule: DeadlineRule, period_year: int, period_month: int) -> date:
    due_year, due_month = _shift_month(period_year, period_month, rule.offset_months)
    base = date(due_year, due_month, _clamp_day(due_year, due_month, rule.due_day_of_month))
    rule_type = DeadlineRuleType(rule.rule_type)
    return get_registry_due_date(rule_type, period_year, period_month, rule.offset_months) or base


def annual_due_date(rule: DeadlineRule, tax_year: int) -> date:
    year, month = _shift_month(tax_year + 1, 1, rule.offset_months)
    return date(year, month, _clamp_day(year, month, rule.due_day_of_month))


def _resolve_rule(
    rule_repo: DeadlineRuleRepository,
    *,
    rule_type: DeadlineRuleType,
    on_date: date,
) -> DeadlineRule:
    rule = rule_repo.resolve_active_rule(rule_type, on_date)
    if rule is None:
        raise MissingDeadlineRuleError(
            f"No active DeadlineRule of type '{rule_type.value}' covering "
            f"{on_date}. Seed the rule before generating tax calendar entries."
        )
    return rule


def _entry_key(
    *,
    obligation_type: ObligationType | str,
    tax_year: int,
    period: str | None,
    period_months_count: int | None,
) -> EntryKey:
    obligation_value = (
        obligation_type.value if isinstance(obligation_type, ObligationType) else obligation_type
    )
    return (obligation_value, tax_year, period, period_months_count)


def _create_entry_if_missing(
    entry_repo: TaxCalendarEntryRepository,
    *,
    existing_keys: set[EntryKey],
    obligation_type: ObligationType,
    period: str | None,
    period_months_count: int | None,
    tax_year: int,
    deadline_rule_id: int,
    due_date: date,
) -> bool:
    key = _entry_key(
        obligation_type=obligation_type,
        tax_year=tax_year,
        period=period,
        period_months_count=period_months_count,
    )
    if key in existing_keys:
        return False

    entry_repo.add(
        TaxCalendarEntry(
            obligation_type=obligation_type,
            period=period,
            period_months_count=period_months_count,
            tax_year=tax_year,
            due_date=due_date,
            deadline_rule_id=deadline_rule_id,
        )
    )
    existing_keys.add(key)
    return True


def _generate_periodic(
    rule_repo: DeadlineRuleRepository,
    entry_repo: TaxCalendarEntryRepository,
    *,
    obligation_type: ObligationType,
    rule_type: DeadlineRuleType,
    tax_year: int,
    period_starts: list[int],
    period_months_count: int,
    existing_keys: set[EntryKey],
) -> tuple[int, int]:
    for m in period_starts:
        if (m - 1) % period_months_count != 0:
            raise ValueError(
                f"period start month {m} is not aligned to period_months_count={period_months_count}"
            )
    rule = _resolve_rule(rule_repo, rule_type=rule_type, on_date=date(tax_year, 1, 1))
    created = 0
    skipped = 0
    for start_month in period_starts:
        period = f"{tax_year}-{start_month:02d}"
        due = periodic_due_date(rule, tax_year, start_month)
        was_created = _create_entry_if_missing(
            entry_repo,
            existing_keys=existing_keys,
            obligation_type=obligation_type,
            period=period,
            period_months_count=period_months_count,
            tax_year=tax_year,
            deadline_rule_id=rule.id,
            due_date=due,
        )
        if was_created:
            created += 1
        else:
            skipped += 1
    return created, skipped


def _generate_for_year(
    rule_repo: DeadlineRuleRepository,
    entry_repo: TaxCalendarEntryRepository,
    *,
    tax_year: int,
    existing_keys: set[EntryKey],
) -> YearGenerationResult:
    total_created = 0
    total_skipped = 0
    for obligation, rule_type, period_starts, months_count in _PERIODIC_PLAN:
        c, s = _generate_periodic(
            rule_repo,
            entry_repo,
            obligation_type=obligation,
            rule_type=rule_type,
            tax_year=tax_year,
            period_starts=period_starts,
            period_months_count=months_count,
            existing_keys=existing_keys,
        )
        total_created += c
        total_skipped += s

    annual_rule = _resolve_rule(
        rule_repo,
        rule_type=DeadlineRuleType.ANNUAL_REPORT,
        on_date=date(tax_year + 1, 1, 1),
    )
    annual_created = _create_entry_if_missing(
        entry_repo,
        existing_keys=existing_keys,
        obligation_type=ObligationType.ANNUAL_REPORT,
        period=None,
        period_months_count=None,
        tax_year=tax_year,
        deadline_rule_id=annual_rule.id,
        due_date=annual_due_date(annual_rule, tax_year),
    )
    if annual_created:
        total_created += 1
    else:
        total_skipped += 1
    return YearGenerationResult(created=total_created, skipped=total_skipped)


def generate_for_year(db: Session, tax_year: int) -> YearGenerationResult:
    """Generate every regulatory calendar entry for a tax year. Idempotent."""
    rule_repo = DeadlineRuleRepository(db)
    entry_repo = TaxCalendarEntryRepository(db)
    existing_keys = entry_repo.load_existing_keys(
        start_year=tax_year,
        end_year=tax_year,
        generated_obligation_values=_GENERATED_OBLIGATION_VALUES,
    )
    result = _generate_for_year(
        rule_repo, entry_repo, tax_year=tax_year, existing_keys=existing_keys
    )
    entry_repo.flush()
    return result


def generate_for_year_range(
    db: Session,
    *,
    start_year: int,
    end_year: int,
) -> YearRangeResult:
    """Generate for [start_year, end_year] inclusive. Idempotent."""
    if end_year < start_year:
        raise ValueError(f"end_year ({end_year}) must be >= start_year ({start_year}).")
    rule_repo = DeadlineRuleRepository(db)
    entry_repo = TaxCalendarEntryRepository(db)
    total_created = 0
    total_skipped = 0
    existing_keys = entry_repo.load_existing_keys(
        start_year=start_year,
        end_year=end_year,
        generated_obligation_values=_GENERATED_OBLIGATION_VALUES,
    )
    for y in range(start_year, end_year + 1):
        yr = _generate_for_year(rule_repo, entry_repo, tax_year=y, existing_keys=existing_keys)
        total_created += yr.created
        total_skipped += yr.skipped
    entry_repo.flush()
    result = YearRangeResult(entries_created=total_created, entries_skipped=total_skipped)
    EntityAuditWriter(db).record_action(
        ENTITY_TAX_CALENDAR,
        start_year,
        None,
        ACTION_TAX_CALENDAR_GENERATED,
        new_value={
            "start_year": start_year,
            "end_year": end_year,
            "entries_created": result.entries_created,
            "entries_skipped": result.entries_skipped,
        },
        actor_type="system",
        actor_display_name="מערכת",
        metadata_json={
            "start_year": start_year,
            "end_year": end_year,
            "entries_created": result.entries_created,
            "entries_skipped": result.entries_skipped,
        },
    )
    return result
