from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import delete, func, select

from app.common.enums import DeadlineRuleType, ObligationType
from app.tax_calendar.models.tax_calendar_deadline_rule import DeadlineRule
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry
from app.tax_calendar.services.tax_calendar_entry_service import (
    MissingDeadlineRuleError,
    annual_due_date,
    generate_for_year,
    generate_for_year_range,
    periodic_due_date,
)


@pytest.fixture(autouse=True)
def empty_default_tax_calendar(test_db):
    test_db.execute(delete(TaxCalendarEntry))
    test_db.execute(delete(DeadlineRule))
    test_db.commit()


def _seed_rule(
    db,
    *,
    rule_type: DeadlineRuleType,
    due_day_of_month: int,
    offset_months: int,
    effective_from: date = date(2020, 1, 1),
    effective_to: date | None = None,
) -> DeadlineRule:
    rule = DeadlineRule(
        rule_type=rule_type,
        due_day_of_month=due_day_of_month,
        offset_months=offset_months,
        effective_from=effective_from,
        effective_to=effective_to,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _seed_all_rules(db) -> dict[DeadlineRuleType, DeadlineRule]:
    return {
        DeadlineRuleType.VAT_MONTHLY: _seed_rule(
            db,
            rule_type=DeadlineRuleType.VAT_MONTHLY,
            due_day_of_month=15,
            offset_months=1,
        ),
        DeadlineRuleType.VAT_BIMONTHLY: _seed_rule(
            db,
            rule_type=DeadlineRuleType.VAT_BIMONTHLY,
            due_day_of_month=15,
            offset_months=2,
        ),
        DeadlineRuleType.ADVANCE_MONTHLY: _seed_rule(
            db,
            rule_type=DeadlineRuleType.ADVANCE_MONTHLY,
            due_day_of_month=15,
            offset_months=1,
        ),
        DeadlineRuleType.ADVANCE_BIMONTHLY: _seed_rule(
            db,
            rule_type=DeadlineRuleType.ADVANCE_BIMONTHLY,
            due_day_of_month=15,
            offset_months=2,
        ),
        DeadlineRuleType.ANNUAL_REPORT: _seed_rule(
            db,
            rule_type=DeadlineRuleType.ANNUAL_REPORT,
            due_day_of_month=31,
            offset_months=4,
        ),
    }


def _count_entries(
    db,
    *,
    obligation_type: ObligationType,
    period_months_count: int | None = None,
    tax_year: int | None = None,
) -> int:
    stmt = (
        select(func.count())
        .select_from(TaxCalendarEntry)
        .where(
            TaxCalendarEntry.obligation_type == obligation_type.value,
        )
    )
    if period_months_count is not None:
        stmt = stmt.where(TaxCalendarEntry.period_months_count == period_months_count)
    if tax_year is not None:
        stmt = stmt.where(TaxCalendarEntry.tax_year == tax_year)
    return db.scalar(stmt)


# ── pure due-date computation ────────────────────────────────────────────────


def test_periodic_due_date_uses_offset_and_day(test_db):
    # Use a future year not in the registry so the DeadlineRule fallback applies.
    rule = _seed_rule(
        test_db,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        due_day_of_month=15,
        offset_months=1,
    )
    assert periodic_due_date(rule, 2030, 4) == date(2030, 5, 15)


def test_periodic_due_date_wraps_year(test_db):
    rule = _seed_rule(
        test_db,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        due_day_of_month=15,
        offset_months=1,
    )
    assert periodic_due_date(rule, 2030, 12) == date(2031, 1, 15)


def test_periodic_due_date_clamps_to_last_day(test_db):
    # Use a future year not in the registry so the clamping logic is exercised.
    rule = _seed_rule(
        test_db,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        due_day_of_month=31,
        offset_months=1,
    )
    assert periodic_due_date(rule, 2030, 1) == date(2030, 2, 28)


def test_annual_due_date_offsets_into_next_year(test_db):
    rule = _seed_rule(
        test_db,
        rule_type=DeadlineRuleType.ANNUAL_REPORT,
        due_day_of_month=31,
        offset_months=4,
    )
    assert annual_due_date(rule, 2025) == date(2026, 5, 31)


# ── generate_for_year happy path ─────────────────────────────────────────────


def test_vat_monthly_creates_12_entries_per_year(test_db):
    _seed_all_rules(test_db)
    generate_for_year(test_db, 2026)
    test_db.commit()
    assert (
        _count_entries(
            test_db,
            obligation_type=ObligationType.VAT,
            period_months_count=1,
            tax_year=2026,
        )
        == 12
    )


def test_vat_bimonthly_creates_6_entries_per_year(test_db):
    _seed_all_rules(test_db)
    generate_for_year(test_db, 2026)
    test_db.commit()
    assert (
        _count_entries(
            test_db,
            obligation_type=ObligationType.VAT,
            period_months_count=2,
            tax_year=2026,
        )
        == 6
    )


def test_advance_monthly_creates_12_entries_per_year(test_db):
    _seed_all_rules(test_db)
    generate_for_year(test_db, 2026)
    test_db.commit()
    assert (
        _count_entries(
            test_db,
            obligation_type=ObligationType.ADVANCE_PAYMENT,
            period_months_count=1,
            tax_year=2026,
        )
        == 12
    )


def test_advance_bimonthly_creates_6_entries_per_year(test_db):
    _seed_all_rules(test_db)
    generate_for_year(test_db, 2026)
    test_db.commit()
    assert (
        _count_entries(
            test_db,
            obligation_type=ObligationType.ADVANCE_PAYMENT,
            period_months_count=2,
            tax_year=2026,
        )
        == 6
    )


def test_annual_creates_one_entry_per_tax_year(test_db):
    _seed_all_rules(test_db)
    generate_for_year(test_db, 2026)
    test_db.commit()
    annual = test_db.scalars(
        select(TaxCalendarEntry).where(
            TaxCalendarEntry.obligation_type == ObligationType.ANNUAL_REPORT.value,
            TaxCalendarEntry.tax_year == 2026,
        )
    ).all()
    assert len(annual) == 1
    assert annual[0].period is None
    assert annual[0].period_months_count is None


def test_full_year_returns_expected_counts(test_db):
    _seed_all_rules(test_db)
    counts = generate_for_year(test_db, 2026)
    test_db.commit()
    assert counts.created == 37
    assert counts.skipped == 0


# ── monthly + bimonthly coexist on shared due_date ───────────────────────────


def test_monthly_and_bimonthly_share_due_date_remain_separate(test_db):
    """VAT-monthly Apr (filing 18.05) and VAT-bimonthly Mar-Apr (filing 18.05)
    both fall on 2026-05-18 (registry holiday shift) but live as distinct rows by months_count."""
    _seed_all_rules(test_db)
    generate_for_year(test_db, 2026)
    test_db.commit()

    same_due = test_db.scalars(
        select(TaxCalendarEntry).where(
            TaxCalendarEntry.obligation_type == ObligationType.VAT.value,
            TaxCalendarEntry.due_date == date(2026, 5, 18),
        )
    ).all()
    months_counts = sorted(e.period_months_count for e in same_due)
    assert months_counts == [1, 2]
    periods = {e.period for e in same_due}
    assert periods == {"2026-04", "2026-03"}


# ── idempotency at full-generation level ─────────────────────────────────────


def test_rerunning_generation_does_not_duplicate_rows(test_db):
    _seed_all_rules(test_db)
    counts_first = generate_for_year(test_db, 2026)
    test_db.commit()
    counts_second = generate_for_year(test_db, 2026)
    test_db.commit()

    assert counts_first.created == 37
    assert counts_first.skipped == 0
    assert counts_second.created == 0
    assert counts_second.skipped == 37
    total = test_db.scalar(select(func.count()).select_from(TaxCalendarEntry))
    assert total == 12 + 6 + 12 + 6 + 1


def test_year_range_generates_each_year_once(test_db):
    _seed_all_rules(test_db)
    result = generate_for_year_range(test_db, start_year=2026, end_year=2027)
    test_db.commit()
    assert result.entries_created == 74
    assert result.entries_skipped == 0
    total = test_db.scalar(select(func.count()).select_from(TaxCalendarEntry))
    assert total == (12 + 6 + 12 + 6 + 1) * 2


def test_year_range_invalid_bounds_rejected(test_db):
    _seed_all_rules(test_db)
    with pytest.raises(ValueError):
        generate_for_year_range(test_db, start_year=2027, end_year=2026)


# ── missing rule fails clearly ───────────────────────────────────────────────


def test_missing_vat_monthly_rule_fails_clearly(test_db):
    # Seed every rule except VAT_MONTHLY
    for rt in (
        DeadlineRuleType.VAT_BIMONTHLY,
        DeadlineRuleType.ADVANCE_MONTHLY,
        DeadlineRuleType.ADVANCE_BIMONTHLY,
        DeadlineRuleType.ANNUAL_REPORT,
    ):
        _seed_rule(test_db, rule_type=rt, due_day_of_month=15, offset_months=1)

    with pytest.raises(MissingDeadlineRuleError) as exc:
        generate_for_year(test_db, 2026)
    assert "vat_monthly" in str(exc.value)


def test_missing_annual_rule_fails_clearly(test_db):
    for rt in (
        DeadlineRuleType.VAT_MONTHLY,
        DeadlineRuleType.VAT_BIMONTHLY,
        DeadlineRuleType.ADVANCE_MONTHLY,
        DeadlineRuleType.ADVANCE_BIMONTHLY,
    ):
        _seed_rule(test_db, rule_type=rt, due_day_of_month=15, offset_months=1)

    with pytest.raises(MissingDeadlineRuleError) as exc:
        generate_for_year(test_db, 2026)
    assert "annual_report" in str(exc.value)


def test_rule_outside_effective_window_is_treated_as_missing(test_db):
    # Rule effective 2030+, but we generate 2026 → no covering rule.
    _seed_rule(
        test_db,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        due_day_of_month=15,
        offset_months=1,
        effective_from=date(2030, 1, 1),
    )
    for rt in (
        DeadlineRuleType.VAT_BIMONTHLY,
        DeadlineRuleType.ADVANCE_MONTHLY,
        DeadlineRuleType.ADVANCE_BIMONTHLY,
        DeadlineRuleType.ANNUAL_REPORT,
    ):
        _seed_rule(test_db, rule_type=rt, due_day_of_month=15, offset_months=1)

    with pytest.raises(MissingDeadlineRuleError):
        generate_for_year(test_db, 2026)


# ── periodic vs annual identity ──────────────────────────────────────────────


def test_periodic_and_annual_can_coexist_for_same_tax_year(test_db):
    _seed_all_rules(test_db)
    generate_for_year(test_db, 2026)
    test_db.commit()
    periodic = _count_entries(test_db, obligation_type=ObligationType.VAT, tax_year=2026)
    annual = _count_entries(test_db, obligation_type=ObligationType.ANNUAL_REPORT, tax_year=2026)
    assert periodic == 18  # 12 monthly + 6 bimonthly
    assert annual == 1


# ── registry integration: 2026 holiday-shifted dates ────────────────────────


def test_registry_shifts_april_2026_monthly_to_18th(test_db):
    """VAT/advance monthly Apr 2026 must use registry date 2026-05-18, not 2026-05-15."""
    rule = _seed_rule(
        test_db,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        due_day_of_month=15,
        offset_months=1,
    )
    assert periodic_due_date(rule, 2026, 4) == date(2026, 5, 18)


def test_registry_shifts_march_april_2026_bimonthly_to_18th(test_db):
    """VAT bimonthly Mar-Apr 2026: calendar key 2026-04 → 2026-05-18."""
    rule = _seed_rule(
        test_db,
        rule_type=DeadlineRuleType.VAT_BIMONTHLY,
        due_day_of_month=15,
        offset_months=2,
    )
    assert periodic_due_date(rule, 2026, 3) == date(2026, 5, 18)


def test_registry_shifts_advance_april_2026_to_18th(test_db):
    """Advance payment monthly Apr 2026 must match VAT: 2026-05-18."""
    rule = _seed_rule(
        test_db,
        rule_type=DeadlineRuleType.ADVANCE_MONTHLY,
        due_day_of_month=15,
        offset_months=1,
    )
    assert periodic_due_date(rule, 2026, 4) == date(2026, 5, 18)


def test_registry_unshifted_months_stay_on_15th(test_db):
    """Months with no holiday shift (e.g. May 2026) keep the statutory 15th."""
    rule = _seed_rule(
        test_db,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        due_day_of_month=15,
        offset_months=1,
    )
    assert periodic_due_date(rule, 2026, 5) == date(2026, 6, 15)


def test_registry_future_year_falls_back_to_deadline_rule(test_db):
    """Year with no registry data (2030) falls back to DeadlineRule computation."""
    rule = _seed_rule(
        test_db,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        due_day_of_month=15,
        offset_months=1,
    )
    assert periodic_due_date(rule, 2030, 4) == date(2030, 5, 15)


def test_registry_not_applied_to_annual_report_rule(test_db):
    """ANNUAL_REPORT rule type is excluded from registry lookup; uses rule-based date."""
    rule = _seed_rule(
        test_db,
        rule_type=DeadlineRuleType.ANNUAL_REPORT,
        due_day_of_month=31,
        offset_months=4,
    )
    # annual_due_date bypasses registry entirely by design
    assert annual_due_date(rule, 2026) == date(2027, 5, 31)


def test_registry_failure_falls_back_and_logs_warning(test_db, caplog):
    """When the registry call raises, periodic_due_date falls back to DeadlineRule and logs a warning."""
    import logging

    import app.tax_calendar.integrations.tax_rules_registry as registry

    rule = _seed_rule(
        test_db,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        due_day_of_month=15,
        offset_months=1,
    )
    with (
        patch.object(registry, "_registry_periodic", side_effect=RuntimeError("registry down")),
        caplog.at_level(logging.WARNING, logger=registry.__name__),
    ):
        result = periodic_due_date(rule, 2026, 5)

    assert result == date(2026, 6, 15)
    assert any(
        "registry down" in r.message or "registry" in r.message.lower() for r in caplog.records
    )
