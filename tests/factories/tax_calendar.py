from __future__ import annotations

from datetime import date, datetime
from itertools import count
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import (
    DeadlineRuleType,
    ObligationType,
)
from app.tax_calendar.models.tax_calendar_deadline_rule import DeadlineRule
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry
from tests.helpers.factory_utils import (
    TEST_DUE_DATE,
    TEST_TAX_YEAR,
    sequence_period,
)


class TaxCalendarEntryFactory:
    """Model-level TaxCalendarEntry factory."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._sequence = count(1)

    def __call__(
        self,
        *,
        obligation_type: ObligationType = ObligationType.VAT,
        period: str | None = None,
        period_months_count: int | None = None,
        tax_year: int = TEST_TAX_YEAR,
        due_date: date = TEST_DUE_DATE,
        deadline_rule_id: int | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        commit: bool = False,
    ) -> TaxCalendarEntry:
        sequence = next(self._sequence)
        if obligation_type == ObligationType.ANNUAL_REPORT:
            resolved_period = None
            resolved_months_count = None
            rule_type = DeadlineRuleType.ANNUAL_REPORT
        else:
            if period_months_count is not None and period_months_count not in (1, 2):
                raise ValueError("period_months_count must be 1 or 2")
            resolved_period = (
                sequence_period(sequence, start_year=tax_year) if period is None else period
            )
            resolved_months_count = 1 if period_months_count is None else period_months_count
            rule_type = (
                DeadlineRuleType.VAT_BIMONTHLY
                if obligation_type == ObligationType.VAT and resolved_months_count == 2
                else DeadlineRuleType.VAT_MONTHLY
                if obligation_type == ObligationType.VAT
                else DeadlineRuleType.ADVANCE_BIMONTHLY
                if resolved_months_count == 2
                else DeadlineRuleType.ADVANCE_MONTHLY
            )
        if deadline_rule_id is None:
            deadline_rule_id = self.db.scalar(
                select(DeadlineRule.id)
                .where(DeadlineRule.rule_type == rule_type)
                .order_by(DeadlineRule.effective_from.desc())
                .limit(1)
            )
        if deadline_rule_id is None:
            raise ValueError(f"No DeadlineRule exists for {rule_type.value}")
        # Calendar entries are shared office-wide, not per client: uq_tax_calendar_entry_periodic
        # is unique on (obligation_type, period, period_months_count) and
        # uq_tax_calendar_entry_annual on (obligation_type, tax_year). Two work items in the same
        # period must therefore link the same entry rather than insert a duplicate.
        existing_stmt = select(TaxCalendarEntry).where(
            TaxCalendarEntry.obligation_type == obligation_type
        )
        if resolved_period is None:
            existing_stmt = existing_stmt.where(
                TaxCalendarEntry.period.is_(None),
                TaxCalendarEntry.tax_year == tax_year,
            )
        else:
            existing_stmt = existing_stmt.where(
                TaxCalendarEntry.period == resolved_period,
                TaxCalendarEntry.period_months_count == resolved_months_count,
            )
        existing = self.db.scalars(existing_stmt.limit(1)).first()
        if existing is not None:
            conflicts = {
                field: (current, requested)
                for field, current, requested in (
                    ("due_date", existing.due_date, due_date),
                    ("deadline_rule_id", existing.deadline_rule_id, deadline_rule_id),
                )
                if current != requested
            }
            if created_at is not None and existing.created_at != created_at:
                conflicts["created_at"] = (existing.created_at, created_at)
            if updated_at is not None and existing.updated_at != updated_at:
                conflicts["updated_at"] = (existing.updated_at, updated_at)
            if conflicts:
                raise ValueError(
                    f"Existing TaxCalendarEntry conflicts with requested fields: {conflicts}"
                )
            return existing
        entry_fields: dict[str, Any] = {
            "obligation_type": obligation_type,
            "period": resolved_period,
            "period_months_count": resolved_months_count,
            "tax_year": tax_year,
            "due_date": due_date,
            "deadline_rule_id": deadline_rule_id,
            "updated_at": updated_at,
        }
        if created_at is not None:
            entry_fields["created_at"] = created_at
        entry = TaxCalendarEntry(**entry_fields)
        self.db.add(entry)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(entry)
        return entry
