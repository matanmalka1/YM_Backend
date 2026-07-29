"""The closing act, shared by all three tax domains (D-13, D-15, D-20).

Closing is gated: every domain answers the same question — *can this be closed,
and if not, what is missing?* — in the same shape (:class:`ClosingReadiness`).
The per-domain gates differ; the shape and the shared assignee gate do not.

Closing records the same facts everywhere: ``closed_at``, ``closed_by``, and
``closed_late``. "Was it closed late?" is written once, at the close — it is a
historical fact about how the office performed and must not depend on a later
reading of a due date that may itself have moved (D-20).
"""

from datetime import date, datetime

from pydantic import BaseModel

from app.utils.time_utils import israel_date

#: The shared gate (D-15): a closed obligation is a record with an author.
CLOSING_ASSIGNEE_REQUIRED_ISSUE = "לא הוקצה נציג אחראי"


class ClosingReadiness(BaseModel):
    """One "what is missing" shape for all three domains (§4.1.8)."""

    is_ready: bool
    issues: list[str]


def compute_closed_late(closed_at: datetime, due_date: date | None) -> bool | None:
    """Whether the closing act happened past the due date.

    ``None`` when there is no due date (D-32) — never ``False``, or a record
    that could not be late reads as "closed on time".
    """

    if due_date is None:
        return None
    return israel_date(closed_at) > due_date
