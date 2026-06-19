"""DeadlineRule service helpers.

INV-11: DeadlineRule overlap is enforced in the service layer, not by
DB constraint. Two rules of the same rule_type whose effective ranges
overlap are forbidden.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.common.enums import DeadlineRuleType
from app.tax_calendar.repositories.tax_calendar_deadline_rule_repository import (
    DeadlineRuleRepository,
)


def has_overlapping_rule(
    db: Session,
    *,
    rule_type: DeadlineRuleType,
    effective_from: date,
    effective_to: date | None,
    exclude_id: int | None = None,
) -> bool:
    repo = DeadlineRuleRepository(db)
    for existing in repo.list_by_type(rule_type, exclude_id=exclude_id):
        existing_to = existing.effective_to
        # Two ranges [a1, a2] and [b1, b2] overlap iff a1 <= b2 and b1 <= a2,
        # treating null upper bound as +infinity.
        if effective_to is not None and existing.effective_from > effective_to:
            continue
        if existing_to is not None and effective_from > existing_to:
            continue
        return True
    return False
