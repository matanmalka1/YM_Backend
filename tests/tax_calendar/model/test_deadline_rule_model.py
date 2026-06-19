from datetime import date

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.common.enums import DeadlineRuleType
from app.tax_calendar.models.tax_calendar_deadline_rule import DeadlineRule
from app.tax_calendar.services.tax_calendar_deadline_rule_service import has_overlapping_rule


@pytest.fixture(autouse=True)
def empty_default_rules(test_db):
    test_db.execute(delete(DeadlineRule))
    test_db.commit()


def _make_rule(
    *,
    rule_type: DeadlineRuleType = DeadlineRuleType.VAT_MONTHLY,
    due_day_of_month: int = 15,
    offset_months: int = 1,
    effective_from: date = date(2024, 1, 1),
    effective_to: date | None = None,
    description: str | None = None,
) -> DeadlineRule:
    return DeadlineRule(
        rule_type=rule_type,
        due_day_of_month=due_day_of_month,
        offset_months=offset_months,
        effective_from=effective_from,
        effective_to=effective_to,
        description=description,
    )


def test_create_valid_rule_with_open_effective_to(test_db):
    rule = _make_rule()
    test_db.add(rule)
    test_db.commit()
    assert rule.id is not None
    assert rule.effective_to is None


def test_effective_to_null_allowed(test_db):
    rule = _make_rule(effective_to=None)
    test_db.add(rule)
    test_db.commit()
    assert rule.effective_to is None


def test_effective_to_before_effective_from_rejected(test_db):
    rule = _make_rule(
        effective_from=date(2024, 6, 1),
        effective_to=date(2024, 1, 1),
    )
    test_db.add(rule)
    with pytest.raises(IntegrityError):
        test_db.commit()
    test_db.rollback()


def test_due_day_of_month_out_of_range_rejected(test_db):
    rule = _make_rule(due_day_of_month=32)
    test_db.add(rule)
    with pytest.raises(IntegrityError):
        test_db.commit()
    test_db.rollback()


def test_offset_months_negative_rejected(test_db):
    rule = _make_rule(offset_months=-1)
    test_db.add(rule)
    with pytest.raises(IntegrityError):
        test_db.commit()
    test_db.rollback()


def test_overlapping_ranges_same_rule_type_detected(test_db):
    rule_a = _make_rule(
        effective_from=date(2024, 1, 1),
        effective_to=date(2024, 12, 31),
    )
    test_db.add(rule_a)
    test_db.commit()

    overlaps = has_overlapping_rule(
        test_db,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        effective_from=date(2024, 6, 1),
        effective_to=date(2025, 5, 31),
    )
    assert overlaps is True


def test_open_ended_existing_rule_overlaps_any_future_range(test_db):
    rule_a = _make_rule(
        effective_from=date(2024, 1, 1),
        effective_to=None,
    )
    test_db.add(rule_a)
    test_db.commit()

    overlaps = has_overlapping_rule(
        test_db,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        effective_from=date(2030, 1, 1),
        effective_to=date(2030, 12, 31),
    )
    assert overlaps is True


def test_overlapping_ranges_different_rule_type_allowed(test_db):
    rule_a = _make_rule(
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        effective_from=date(2024, 1, 1),
        effective_to=date(2024, 12, 31),
    )
    test_db.add(rule_a)
    test_db.commit()

    overlaps = has_overlapping_rule(
        test_db,
        rule_type=DeadlineRuleType.ADVANCE_MONTHLY,
        effective_from=date(2024, 6, 1),
        effective_to=date(2025, 5, 31),
    )
    assert overlaps is False


def test_overlap_check_excludes_self_by_id(test_db):
    rule = _make_rule(
        effective_from=date(2024, 1, 1),
        effective_to=date(2024, 12, 31),
    )
    test_db.add(rule)
    test_db.commit()

    overlaps = has_overlapping_rule(
        test_db,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        effective_from=date(2024, 1, 1),
        effective_to=date(2024, 12, 31),
        exclude_id=rule.id,
    )
    assert overlaps is False


def test_non_overlapping_disjoint_ranges_pass(test_db):
    rule_a = _make_rule(
        effective_from=date(2024, 1, 1),
        effective_to=date(2024, 6, 30),
    )
    test_db.add(rule_a)
    test_db.commit()

    overlaps = has_overlapping_rule(
        test_db,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        effective_from=date(2024, 7, 1),
        effective_to=date(2024, 12, 31),
    )
    assert overlaps is False
