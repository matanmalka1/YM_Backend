from sqlalchemy import select

from app.tax_calendar.models.tax_calendar_deadline_rule import DeadlineRule
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry
from app.tax_calendar.services.tax_calendar_bootstrap_service import (
    DEFAULT_DEADLINE_RULES,
    bootstrap_tax_calendar,
    seed_default_deadline_rules,
)
from app.tax_calendar.services.tax_calendar_settings_calendar_service import (
    get_summary,
    list_entries,
    list_rules,
)


def test_list_rules_count(test_db):
    seed_default_deadline_rules(test_db)
    test_db.commit()

    rules = list_rules(test_db)
    assert len(rules) == len(DEFAULT_DEADLINE_RULES)
    assert all(isinstance(r, DeadlineRule) for r in rules)


def test_list_rules_ordering(test_db):
    seed_default_deadline_rules(test_db)
    test_db.commit()

    rules = list_rules(test_db)
    keys = [(r.rule_type, r.effective_from) for r in rules]
    assert keys == sorted(keys, key=lambda x: (str(x[0]), x[1]))


def test_list_entries_year_filter(test_db):
    bootstrap_tax_calendar(test_db, start_year=2026, end_year=2027)
    test_db.commit()

    entries = list_entries(test_db, tax_year_after=2026, tax_year_before=2026)
    assert len(entries) == 37
    assert all(e.tax_year == 2026 for e in entries)


def test_list_entries_no_filter(test_db):
    bootstrap_tax_calendar(test_db, start_year=2026, end_year=2027)
    test_db.commit()

    entries = list_entries(test_db, tax_year_after=None, tax_year_before=None)
    assert len(entries) == 74


def test_get_summary_correct_counts(test_db):
    bootstrap_tax_calendar(test_db, start_year=2026, end_year=2027)
    test_db.commit()

    summary = get_summary(test_db, tax_year_after=2026, tax_year_before=2027)

    assert summary["total_entries"] == 74
    assert set(summary["per_year"].keys()) == {2026, 2027}
    for year_data in summary["per_year"].values():
        assert sum(year_data.values()) == 37
    # count-based warnings should be absent; only fallback warnings possible
    count_warnings = [w for w in summary["warnings"] if "fallback" not in w]
    assert count_warnings == []


def test_get_summary_2026_no_fallback_warning(test_db):
    bootstrap_tax_calendar(test_db, start_year=2026, end_year=2026)
    test_db.commit()

    summary = get_summary(test_db, tax_year_after=2026, tax_year_before=2026)
    assert not any("fallback" in w for w in summary["warnings"])


def test_get_summary_reports_registry_fallback_warning(test_db, monkeypatch):
    monkeypatch.setattr(
        "app.tax_calendar.services.tax_calendar_settings_calendar_service.missing_registry_years",
        lambda _start_year, _end_year: [2027],
    )
    bootstrap_tax_calendar(test_db, start_year=2027, end_year=2027)
    test_db.commit()

    summary = get_summary(test_db, tax_year_after=2027, tax_year_before=2027)
    assert summary["total_entries"] == 37
    assert any("2027" in w and "fallback" in w for w in summary["warnings"])


def test_bootstrap_2027_succeeds(test_db):
    """Bootstrap must not raise even when 2027 registry calendar is absent."""
    result = bootstrap_tax_calendar(test_db, start_year=2027, end_year=2027)
    test_db.commit()
    assert result["entries_created"] + result["entries_skipped"] == 37


def test_get_summary_detects_missing_entry(test_db):
    bootstrap_tax_calendar(test_db, start_year=2026, end_year=2026)
    test_db.commit()

    entry = test_db.scalars(
        select(TaxCalendarEntry).where(TaxCalendarEntry.tax_year == 2026)
    ).first()
    test_db.delete(entry)
    test_db.commit()

    summary = get_summary(test_db, tax_year_after=2026, tax_year_before=2026)
    assert len(summary["warnings"]) >= 1
    assert "2026" in summary["warnings"][0]


def test_get_summary_empty_db_has_warnings(test_db):
    summary = get_summary(test_db, tax_year_after=2026, tax_year_before=2026)
    assert summary["total_entries"] == 0
    assert len(summary["warnings"]) > 0
