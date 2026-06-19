from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import DeadlineRuleType
from app.tax_calendar.models.tax_calendar_deadline_rule import DeadlineRule


class DeadlineRuleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def has_open_ended_rule(self, rule_type: DeadlineRuleType) -> bool:
        return (
            self.db.scalar(
                select(DeadlineRule.id).where(
                    DeadlineRule.rule_type == rule_type.value,
                    DeadlineRule.effective_to.is_(None),
                )
            )
            is not None
        )

    def list_by_type(
        self,
        rule_type: DeadlineRuleType,
        *,
        exclude_id: int | None = None,
    ) -> list[DeadlineRule]:
        stmt = select(DeadlineRule).where(DeadlineRule.rule_type == rule_type.value)
        if exclude_id is not None:
            stmt = stmt.where(DeadlineRule.id != exclude_id)
        return list(self.db.scalars(stmt).all())

    def resolve_active_rule(
        self,
        rule_type: DeadlineRuleType,
        on_date: date,
    ) -> DeadlineRule | None:
        return self.db.scalars(
            select(DeadlineRule)
            .where(DeadlineRule.rule_type == rule_type.value)
            .where(DeadlineRule.effective_from <= on_date)
            .where((DeadlineRule.effective_to.is_(None)) | (DeadlineRule.effective_to >= on_date))
            .order_by(DeadlineRule.effective_from.desc())
            .limit(1)
        ).first()

    def add(self, rule: DeadlineRule) -> None:
        self.db.add(rule)

    def flush(self) -> None:
        self.db.flush()
