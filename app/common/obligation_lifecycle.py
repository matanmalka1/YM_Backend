"""The one transition graph every tax obligation moves through.

VAT and annual reports each carried their own ``VALID_TRANSITIONS`` table, and
advance payments had no graph at all — their status was derived from money, so a
turnover change could silently move a settled period backwards. The three now share
this module.

The rules, and why each exists:

- **Forward, one stage at a time.** Stages have an order and skipping one loses the
  record of what actually happened.
- **An event may perform consecutive transitions**, and records each. Recording a
  payment on an advance still waiting for its turnover moves it 1 → 2 → 3: two
  transitions, both real, not a jump over stage 2.
- **Backward, one stage at a time, and always with a reason.** Backward movement is
  kept single-step so the history stays readable, and a readable history without a
  "why" is half a history.
- **Only a person locks.** ``SUBMITTED`` has no outgoing transition; correcting a
  submitted obligation creates an amendment (W4), it never reopens the record.
- **Cancel from any unlocked stage.** Not from ``SUBMITTED``: a submitted period is
  the record of a filing. ``CANCELED`` is terminal — a returning client gets the
  period created fresh rather than the old row revived.
"""

from app.common.enums import ObligationStatus
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError

#: The ladder, in order. ``CANCELED`` is deliberately absent — it is reachable from
#: any unlocked stage and holds no position on the ladder.
ORDERED_STAGES: tuple[ObligationStatus, ...] = (
    ObligationStatus.AWAITING_INPUT,
    ObligationStatus.INPUT_RECEIVED,
    ObligationStatus.IN_PROGRESS,
    ObligationStatus.AWAITING_VERIFICATION,
    ObligationStatus.SUBMITTED,
)

_STAGE_INDEX: dict[ObligationStatus, int] = {
    status: index for index, status in enumerate(ORDERED_STAGES)
}

INVALID_TRANSITION_MESSAGE = "לא ניתן לעבור מסטטוס {current} לסטטוס {target}"
LOCKED_MESSAGE = "הרשומה הוגשה ואינה ניתנת לשינוי — יש ליצור תיקון"
CANCELED_MESSAGE = "הרשומה בוטלה ואינה ניתנת לשינוי"
BACKWARD_REASON_REQUIRED_MESSAGE = "נדרשת סיבה כדי להחזיר את הרשומה לשלב קודם"
SKIPPED_STAGE_MESSAGE = "לא ניתן לדלג על שלב — יש לעבור שלב אחד בכל פעם"


def stage_index(status: ObligationStatus) -> int:
    """Position on the ladder. Raises for ``CANCELED``, which has none."""
    try:
        return _STAGE_INDEX[status]
    except KeyError as exc:
        raise ValueError(f"{status} is off-ladder and has no stage index") from exc


def is_locked(status: ObligationStatus) -> bool:
    """A locked obligation cannot change at all — only an amendment can correct it."""
    return status == ObligationStatus.SUBMITTED


def is_terminal(status: ObligationStatus) -> bool:
    """No outgoing transitions of any kind."""
    return status in (ObligationStatus.SUBMITTED, ObligationStatus.CANCELED)


def next_stage(status: ObligationStatus) -> ObligationStatus | None:
    """The single stage forward, or None at the end of the ladder."""
    if status == ObligationStatus.CANCELED:
        return None
    index = stage_index(status)
    return ORDERED_STAGES[index + 1] if index + 1 < len(ORDERED_STAGES) else None


def previous_stage(status: ObligationStatus) -> ObligationStatus | None:
    """The single stage back, or None at the start of the ladder."""
    if status == ObligationStatus.CANCELED:
        return None
    index = stage_index(status)
    return ORDERED_STAGES[index - 1] if index > 0 else None


def allowed_transitions(status: ObligationStatus) -> frozenset[ObligationStatus]:
    """Every status reachable from ``status`` in one move."""
    if is_terminal(status):
        return frozenset()
    reachable = {ObligationStatus.CANCELED}
    forward = next_stage(status)
    if forward is not None:
        reachable.add(forward)
    backward = previous_stage(status)
    if backward is not None:
        reachable.add(backward)
    return frozenset(reachable)


def is_backward(current: ObligationStatus, target: ObligationStatus) -> bool:
    """Whether this move goes back down the ladder."""
    if target == ObligationStatus.CANCELED or current == ObligationStatus.CANCELED:
        return False
    return stage_index(target) < stage_index(current)


def assert_transition_allowed(
    current: ObligationStatus,
    target: ObligationStatus,
    *,
    reason: str | None = None,
) -> None:
    """Raise unless ``current`` may move to ``target`` in a single step.

    ``reason`` is required for any backward move and ignored otherwise. Callers that
    advance several stages on one event call this once per step, so each transition
    is validated and recorded on its own.
    """
    if current == target:
        raise AppError(
            INVALID_TRANSITION_MESSAGE.format(current=current.value, target=target.value),
            ErrorCode.OBLIGATION_INVALID_TRANSITION,
        )
    if current == ObligationStatus.SUBMITTED:
        raise AppError(LOCKED_MESSAGE, ErrorCode.OBLIGATION_LOCKED)
    if current == ObligationStatus.CANCELED:
        raise AppError(CANCELED_MESSAGE, ErrorCode.OBLIGATION_INVALID_TRANSITION)

    if target == ObligationStatus.CANCELED:
        return

    distance = stage_index(target) - stage_index(current)
    if abs(distance) != 1:
        raise AppError(SKIPPED_STAGE_MESSAGE, ErrorCode.OBLIGATION_INVALID_TRANSITION)

    if distance < 0 and not (reason or "").strip():
        raise AppError(
            BACKWARD_REASON_REQUIRED_MESSAGE,
            ErrorCode.OBLIGATION_TRANSITION_REASON_REQUIRED,
        )


def stages_between(
    current: ObligationStatus, target: ObligationStatus
) -> tuple[ObligationStatus, ...]:
    """Each stage an event must step through to reach ``target``, in order.

    Forward only. This is what lets one event perform consecutive transitions
    without skipping a stage's meaning: recording a payment on an advance still at
    ``AWAITING_INPUT`` returns ``(INPUT_RECEIVED, IN_PROGRESS)``, and the caller
    applies and records both.
    """
    if is_terminal(current) or target == ObligationStatus.CANCELED:
        return ()
    start, end = stage_index(current), stage_index(target)
    if end <= start:
        return ()
    return ORDERED_STAGES[start + 1 : end + 1]


__all__ = [
    "ORDERED_STAGES",
    "allowed_transitions",
    "assert_transition_allowed",
    "is_backward",
    "is_locked",
    "is_terminal",
    "next_stage",
    "previous_stage",
    "stage_index",
    "stages_between",
]
