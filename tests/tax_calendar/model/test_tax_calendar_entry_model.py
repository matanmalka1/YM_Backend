from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.common.enums import DeadlineRuleType, ObligationType
from app.tax_calendar.models.tax_calendar_deadline_rule import DeadlineRule
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry


def _make_rule(test_db, rule_type: DeadlineRuleType, *, due_day_of_month: int = 15) -> DeadlineRule:
    existing = test_db.scalars(
        select(DeadlineRule).where(
            DeadlineRule.rule_type == rule_type.value,
            DeadlineRule.effective_to.is_(None),
        )
    ).first()
    if existing is not None:
        return existing
    rule = DeadlineRule(
        rule_type=rule_type,
        due_day_of_month=due_day_of_month,
        offset_months=1,
        effective_from=date(2024, 1, 1),
        effective_to=None,
    )
    test_db.add(rule)
    test_db.commit()
    test_db.refresh(rule)
    return rule


def _make_entry(
    *,
    rule: DeadlineRule,
    obligation_type: ObligationType,
    period: str | None,
    period_months_count: int | None,
    tax_year: int,
    due_date: date = date(2026, 5, 15),
) -> TaxCalendarEntry:
    return TaxCalendarEntry(
        obligation_type=obligation_type,
        period=period,
        period_months_count=period_months_count,
        tax_year=tax_year,
        due_date=due_date,
        deadline_rule_id=rule.id,
    )


def test_create_valid_periodic_vat_entry(test_db):
    rule = _make_rule(test_db, DeadlineRuleType.VAT_MONTHLY)
    entry = _make_entry(
        rule=rule,
        obligation_type=ObligationType.VAT,
        period="2026-04",
        period_months_count=1,
        tax_year=2026,
    )
    test_db.add(entry)
    test_db.commit()
    assert entry.id is not None


def test_create_valid_annual_entry(test_db):
    rule = _make_rule(test_db, DeadlineRuleType.ANNUAL_REPORT, due_day_of_month=30)
    entry = _make_entry(
        rule=rule,
        obligation_type=ObligationType.ANNUAL_REPORT,
        period=None,
        period_months_count=None,
        tax_year=2025,
        due_date=date(2026, 4, 30),
    )
    test_db.add(entry)
    test_db.commit()
    assert entry.id is not None


def test_vat_with_null_period_rejected(test_db):
    rule = _make_rule(test_db, DeadlineRuleType.VAT_MONTHLY)
    entry = _make_entry(
        rule=rule,
        obligation_type=ObligationType.VAT,
        period=None,
        period_months_count=1,
        tax_year=2026,
    )
    test_db.add(entry)
    with pytest.raises((ValueError, IntegrityError)):
        test_db.commit()
    test_db.rollback()


def test_advance_payment_with_null_period_rejected(test_db):
    rule = _make_rule(test_db, DeadlineRuleType.ADVANCE_MONTHLY)
    entry = _make_entry(
        rule=rule,
        obligation_type=ObligationType.ADVANCE_PAYMENT,
        period=None,
        period_months_count=1,
        tax_year=2026,
    )
    test_db.add(entry)
    with pytest.raises((ValueError, IntegrityError)):
        test_db.commit()
    test_db.rollback()


def test_national_insurance_with_null_period_rejected(test_db):
    rule = _make_rule(test_db, DeadlineRuleType.VAT_MONTHLY)
    entry = _make_entry(
        rule=rule,
        obligation_type=ObligationType.NATIONAL_INSURANCE,
        period=None,
        period_months_count=1,
        tax_year=2026,
    )
    test_db.add(entry)
    with pytest.raises((ValueError, IntegrityError)) as exc:
        test_db.commit()
    test_db.rollback()
    assert "NATIONAL_INSURANCE" in str(exc.value) or "national_insurance" in str(exc.value)


def test_national_insurance_even_with_period_is_unsupported(test_db):
    rule = _make_rule(test_db, DeadlineRuleType.VAT_MONTHLY)
    entry = _make_entry(
        rule=rule,
        obligation_type=ObligationType.NATIONAL_INSURANCE,
        period="2026-04",
        period_months_count=1,
        tax_year=2026,
    )
    test_db.add(entry)
    with pytest.raises(ValueError) as exc:
        test_db.commit()
    test_db.rollback()
    assert "NATIONAL_INSURANCE is not yet supported" in str(exc.value)


def test_vat_with_null_months_count_rejected(test_db):
    rule = _make_rule(test_db, DeadlineRuleType.VAT_MONTHLY)
    entry = _make_entry(
        rule=rule,
        obligation_type=ObligationType.VAT,
        period="2026-04",
        period_months_count=None,
        tax_year=2026,
    )
    test_db.add(entry)
    with pytest.raises((ValueError, IntegrityError)):
        test_db.commit()
    test_db.rollback()


def test_advance_payment_with_null_months_count_rejected(test_db):
    rule = _make_rule(test_db, DeadlineRuleType.ADVANCE_MONTHLY)
    entry = _make_entry(
        rule=rule,
        obligation_type=ObligationType.ADVANCE_PAYMENT,
        period="2026-04",
        period_months_count=None,
        tax_year=2026,
    )
    test_db.add(entry)
    with pytest.raises((ValueError, IntegrityError)):
        test_db.commit()
    test_db.rollback()


def test_annual_report_with_non_null_period_rejected(test_db):
    rule = _make_rule(test_db, DeadlineRuleType.ANNUAL_REPORT, due_day_of_month=30)
    entry = _make_entry(
        rule=rule,
        obligation_type=ObligationType.ANNUAL_REPORT,
        period="2025-12",
        period_months_count=None,
        tax_year=2025,
        due_date=date(2026, 4, 30),
    )
    test_db.add(entry)
    with pytest.raises((ValueError, IntegrityError)):
        test_db.commit()
    test_db.rollback()


def test_annual_report_with_non_null_months_count_rejected(test_db):
    rule = _make_rule(test_db, DeadlineRuleType.ANNUAL_REPORT, due_day_of_month=30)
    entry = _make_entry(
        rule=rule,
        obligation_type=ObligationType.ANNUAL_REPORT,
        period=None,
        period_months_count=1,
        tax_year=2025,
        due_date=date(2026, 4, 30),
    )
    test_db.add(entry)
    with pytest.raises((ValueError, IntegrityError)):
        test_db.commit()
    test_db.rollback()


@pytest.mark.parametrize("bad_period", ["2026-13", "26-05", "2026/05", "2026-1", "abcd-ef"])
def test_invalid_period_format_rejected(test_db, bad_period):
    rule = _make_rule(test_db, DeadlineRuleType.VAT_MONTHLY)
    with pytest.raises(ValueError):
        TaxCalendarEntry(
            obligation_type=ObligationType.VAT,
            period=bad_period,
            period_months_count=1,
            tax_year=2026,
            due_date=date(2026, 5, 15),
            deadline_rule_id=rule.id,
        )


@pytest.mark.parametrize("bad_count", [0, 3, -1, 12])
def test_invalid_months_count_rejected_at_assignment(test_db, bad_count):
    rule = _make_rule(test_db, DeadlineRuleType.VAT_MONTHLY)
    with pytest.raises(ValueError):
        TaxCalendarEntry(
            obligation_type=ObligationType.VAT,
            period="2026-04",
            period_months_count=bad_count,
            tax_year=2026,
            due_date=date(2026, 5, 15),
            deadline_rule_id=rule.id,
        )


def test_period_year_must_match_tax_year(test_db):
    rule = _make_rule(test_db, DeadlineRuleType.VAT_MONTHLY)
    entry = _make_entry(
        rule=rule,
        obligation_type=ObligationType.VAT,
        period="2026-12",
        period_months_count=1,
        tax_year=2027,
    )
    test_db.add(entry)
    with pytest.raises(ValueError) as exc:
        test_db.commit()
    test_db.rollback()
    assert "tax_year" in str(exc.value)


def test_duplicate_periodic_entry_rejected(test_db):
    rule = _make_rule(test_db, DeadlineRuleType.VAT_MONTHLY)
    e1 = _make_entry(
        rule=rule,
        obligation_type=ObligationType.VAT,
        period="2026-04",
        period_months_count=1,
        tax_year=2026,
    )
    test_db.add(e1)
    test_db.commit()

    e2 = _make_entry(
        rule=rule,
        obligation_type=ObligationType.VAT,
        period="2026-04",
        period_months_count=1,
        tax_year=2026,
        due_date=date(2026, 5, 19),
    )
    test_db.add(e2)
    with pytest.raises(IntegrityError):
        test_db.commit()
    test_db.rollback()


def test_duplicate_annual_entry_rejected(test_db):
    rule = _make_rule(test_db, DeadlineRuleType.ANNUAL_REPORT, due_day_of_month=30)
    e1 = _make_entry(
        rule=rule,
        obligation_type=ObligationType.ANNUAL_REPORT,
        period=None,
        period_months_count=None,
        tax_year=2025,
        due_date=date(2026, 4, 30),
    )
    test_db.add(e1)
    test_db.commit()

    e2 = _make_entry(
        rule=rule,
        obligation_type=ObligationType.ANNUAL_REPORT,
        period=None,
        period_months_count=None,
        tax_year=2025,
        due_date=date(2026, 5, 31),
    )
    test_db.add(e2)
    with pytest.raises(IntegrityError):
        test_db.commit()
    test_db.rollback()


def test_periodic_unique_does_not_block_different_months_count(test_db):
    rule_m = _make_rule(test_db, DeadlineRuleType.VAT_MONTHLY)
    rule_b = _make_rule(test_db, DeadlineRuleType.VAT_BIMONTHLY)

    e1 = _make_entry(
        rule=rule_m,
        obligation_type=ObligationType.VAT,
        period="2026-04",
        period_months_count=1,
        tax_year=2026,
    )
    test_db.add(e1)
    test_db.commit()

    e2 = _make_entry(
        rule=rule_b,
        obligation_type=ObligationType.VAT,
        period="2026-04",
        period_months_count=2,
        tax_year=2026,
    )
    test_db.add(e2)
    test_db.commit()
    assert e2.id is not None


def test_rule_compatibility_vat_rejects_advance_rule(test_db):
    bad_rule = _make_rule(test_db, DeadlineRuleType.ADVANCE_MONTHLY)
    entry = _make_entry(
        rule=bad_rule,
        obligation_type=ObligationType.VAT,
        period="2026-04",
        period_months_count=1,
        tax_year=2026,
    )
    test_db.add(entry)
    with pytest.raises(ValueError) as exc:
        test_db.commit()
    test_db.rollback()
    assert "not compatible" in str(exc.value)


def test_rule_compatibility_advance_rejects_vat_rule(test_db):
    bad_rule = _make_rule(test_db, DeadlineRuleType.VAT_MONTHLY)
    entry = _make_entry(
        rule=bad_rule,
        obligation_type=ObligationType.ADVANCE_PAYMENT,
        period="2026-04",
        period_months_count=1,
        tax_year=2026,
    )
    test_db.add(entry)
    with pytest.raises(ValueError) as exc:
        test_db.commit()
    test_db.rollback()
    assert "not compatible" in str(exc.value)


def test_rule_compatibility_annual_rejects_periodic_rule(test_db):
    bad_rule = _make_rule(test_db, DeadlineRuleType.VAT_MONTHLY)
    entry = _make_entry(
        rule=bad_rule,
        obligation_type=ObligationType.ANNUAL_REPORT,
        period=None,
        period_months_count=None,
        tax_year=2025,
        due_date=date(2026, 4, 30),
    )
    test_db.add(entry)
    with pytest.raises(ValueError) as exc:
        test_db.commit()
    test_db.rollback()
    assert "not compatible" in str(exc.value)


def test_periodic_unique_does_not_block_annual_with_same_tax_year(test_db):
    vat_rule = _make_rule(test_db, DeadlineRuleType.VAT_MONTHLY)
    annual_rule = _make_rule(test_db, DeadlineRuleType.ANNUAL_REPORT, due_day_of_month=30)

    periodic = _make_entry(
        rule=vat_rule,
        obligation_type=ObligationType.VAT,
        period="2025-12",
        period_months_count=1,
        tax_year=2025,
    )
    annual = _make_entry(
        rule=annual_rule,
        obligation_type=ObligationType.ANNUAL_REPORT,
        period=None,
        period_months_count=None,
        tax_year=2025,
        due_date=date(2026, 4, 30),
    )
    test_db.add_all([periodic, annual])
    test_db.commit()
    assert periodic.id is not None
    assert annual.id is not None
