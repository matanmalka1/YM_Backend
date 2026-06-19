from datetime import date

from sqlalchemy import delete, func, select

from app.tax_calendar.integrations.tax_rules_registry import (
    registry_periodic_calendar_available,
)
from app.tax_calendar.models.tax_calendar_deadline_rule import DeadlineRule
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry
from app.tax_calendar.services.tax_calendar_bootstrap import (
    DEFAULT_DEADLINE_RULES,
    DEFAULT_EFFECTIVE_FROM,
    EXPECTED_ENTRIES_PER_YEAR,
    bootstrap_tax_calendar,
    seed_default_deadline_rules,
)

_EXPECTED_RULE_KEYS = {d.rule_type.value for d in DEFAULT_DEADLINE_RULES}


def _clear_tax_calendar(db) -> None:
    db.execute(delete(TaxCalendarEntry))
    db.execute(delete(DeadlineRule))
    db.commit()


def _rule_count(db) -> int:
    return db.scalar(select(func.count()).select_from(DeadlineRule))


def _entry_count(db) -> int:
    return db.scalar(select(func.count()).select_from(TaxCalendarEntry))


def test_default_rules_are_created_when_missing(test_db):
    _clear_tax_calendar(test_db)
    result = seed_default_deadline_rules(test_db)
    test_db.commit()

    assert result.created == 5
    assert result.skipped == 0
    assert set(result.by_rule_type.values()) == {"created"}
    assert set(result.by_rule_type.keys()) == _EXPECTED_RULE_KEYS
    assert _rule_count(test_db) == 5
    rules = test_db.scalars(select(DeadlineRule)).all()
    assert {r.rule_type for r in rules} == _EXPECTED_RULE_KEYS
    assert {r.effective_from for r in rules} == {DEFAULT_EFFECTIVE_FROM}
    assert {r.effective_to for r in rules} == {None}


def test_default_rules_are_not_duplicated_on_rerun(test_db):
    seed_default_deadline_rules(test_db)
    test_db.commit()
    result = seed_default_deadline_rules(test_db)
    test_db.commit()

    assert result.created == 0
    assert result.skipped == 5
    assert set(result.by_rule_type.values()) == {"skipped"}
    assert _rule_count(test_db) == 5


def test_bootstrap_generates_entries_for_requested_year_range(test_db):
    result = bootstrap_tax_calendar(test_db, start_year=2026, end_year=2027)
    test_db.commit()

    assert result["start_year"] == 2026
    assert result["end_year"] == 2027
    assert result["entries_created"] == 74
    assert result["entries_skipped"] == 0
    assert result["total_entries_for_range"] == 74
    assert result["warnings"] == []
    assert _entry_count(test_db) == 74


def test_bootstrap_rerun_creates_zero_new_entries(test_db):
    bootstrap_tax_calendar(test_db, start_year=2026, end_year=2026)
    test_db.commit()
    result = bootstrap_tax_calendar(test_db, start_year=2026, end_year=2026)
    test_db.commit()

    assert result["rules_created"] == 0
    assert result["rules_skipped"] == 5
    assert result["entries_created"] == 0
    assert result["entries_skipped"] == 37
    assert result["total_entries_for_range"] == 37
    assert _entry_count(test_db) == 37


def test_bootstrap_default_year_range_uses_only_supported_registry_years(test_db):
    result = bootstrap_tax_calendar(test_db, today=date(2026, 5, 7))
    test_db.commit()

    assert result["start_year"] == 2026
    expected_end = 2027 if registry_periodic_calendar_available(2027) else 2026
    assert result["end_year"] == expected_end


def test_bootstrap_rules_by_type_detail(test_db):
    _clear_tax_calendar(test_db)
    result = bootstrap_tax_calendar(test_db, start_year=2026, end_year=2026)
    test_db.commit()

    assert set(result["rules_by_type"].keys()) == _EXPECTED_RULE_KEYS
    assert set(result["rules_by_type"].values()) == {"created"}


def test_bootstrap_total_entries_two_year_range(test_db):
    result = bootstrap_tax_calendar(test_db, start_year=2026, end_year=2027)
    test_db.commit()

    assert result["total_entries_for_range"] == EXPECTED_ENTRIES_PER_YEAR * 2
    assert result["warnings"] == []


def test_bootstrap_recreates_missing_entries_without_warning(test_db):
    bootstrap_tax_calendar(test_db, start_year=2026, end_year=2026)
    test_db.commit()

    to_delete = test_db.scalars(
        select(TaxCalendarEntry).where(TaxCalendarEntry.tax_year == 2026).limit(5)
    ).all()
    for e in to_delete:
        test_db.delete(e)
    test_db.commit()
    assert _entry_count(test_db) == 32

    result2 = bootstrap_tax_calendar(test_db, start_year=2026, end_year=2026)
    test_db.commit()

    assert result2["entries_created"] == 5
    assert result2["total_entries_for_range"] == EXPECTED_ENTRIES_PER_YEAR
    assert result2["warnings"] == []
    assert _entry_count(test_db) == 37


def test_bootstrap_idempotency_no_integrity_error(test_db):
    bootstrap_tax_calendar(test_db, start_year=2026, end_year=2026)
    test_db.commit()
    # Second run must not raise
    result = bootstrap_tax_calendar(test_db, start_year=2026, end_year=2026)
    test_db.commit()
    assert result["entries_created"] == 0
    assert result["total_entries_for_range"] == EXPECTED_ENTRIES_PER_YEAR
