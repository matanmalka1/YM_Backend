from datetime import date
from types import SimpleNamespace

import pytest

from app.common.enums import SubmissionMethod
from app.vat.services.vat_report_queries import (
    deadline_fields_from_snapshot,
    get_vat_deadline_fields,
)


def _snapshot_item(effective, original=None, period="2026-08"):
    return SimpleNamespace(
        due_date_effective=effective,
        due_date_original=original,
        period_type=SimpleNamespace(value="monthly"),
        period=period,
    )


class TestDeadlineFieldsFromSnapshot:
    def test_submission_equals_effective_regardless_of_method(self):
        # due_date_effective already incorporates any calendar extension;
        # snapshot path must NOT add online-extension days on top.
        effective = date(2026, 9, 24)
        for method in (None, SubmissionMethod.ONLINE, SubmissionMethod.MANUAL):
            result = deadline_fields_from_snapshot(
                _snapshot_item(effective), submission_method=method
            )
            assert result["submission_deadline"] == effective, f"failed for method={method}"
            assert result["extended_deadline"] == effective, (
                f"extended mismatch for method={method}"
            )
            assert result["statutory_deadline"] == effective

    def test_regression_2026_08_exception_no_double_extension(self):
        # 2026-08: calendar exception already sets effective=2026-09-24.
        # Snapshot path must return 2026-09-24, not 2026-09-28.
        effective = date(2026, 9, 24)
        result = deadline_fields_from_snapshot(
            _snapshot_item(effective, period="2026-08"),
            submission_method=SubmissionMethod.ONLINE,
        )
        assert result["submission_deadline"] == date(2026, 9, 24)

    def test_overridden_item_statutory_shows_original_registry_date(self):
        # due_date_original = registry statutory; due_date_effective = override.
        # statutory_deadline must reflect the original, not the override.
        original = date(2026, 9, 24)
        effective = date(2026, 10, 1)
        result = deadline_fields_from_snapshot(
            _snapshot_item(effective, original=original), submission_method=None
        )
        assert result["statutory_deadline"] == original
        assert result["submission_deadline"] == effective
        assert result["extended_deadline"] == effective

    def test_snapshot_path_does_not_access_period(self):
        class _NoPeriodItem:
            due_date_effective = date(2026, 9, 24)
            due_date_original = date(2026, 9, 24)

            @property
            def period(self):
                raise AssertionError("deadline_fields_from_snapshot must not access item.period")

        result = deadline_fields_from_snapshot(
            _NoPeriodItem(), submission_method=SubmissionMethod.ONLINE
        )
        assert result["submission_deadline"] == date(2026, 9, 24)


class TestGetVatDeadlineFields:
    def test_routes_to_snapshot_when_effective_set(self):
        effective = date(2026, 9, 24)
        item = _snapshot_item(effective, original=effective)
        result = get_vat_deadline_fields(item, SubmissionMethod.ONLINE)
        # Snapshot path: no extra extension — effective IS the deadline.
        assert result["submission_deadline"] == effective
        assert result["statutory_deadline"] == effective

    def test_missing_effective_due_date_raises(self):
        class _Item:
            id = 123
            due_date_effective = None

        with pytest.raises(ValueError, match="missing due_date_effective"):
            get_vat_deadline_fields(_Item(), SubmissionMethod.MANUAL)
