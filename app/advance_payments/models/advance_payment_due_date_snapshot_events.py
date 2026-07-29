"""SQLAlchemy events for advance payment due-date snapshots."""

from sqlalchemy import event, inspect

from app.advance_payments.models.advance_payment import AdvancePayment


def _default_due_date_snapshots(target: AdvancePayment) -> None:
    # An amendment has no deadline (D-14). Without this guard the backfill below
    # would manufacture one from ``due_date`` and put every correction back on
    # the overdue list — the exclusion in ``obligation_chain`` cannot prevent it,
    # because this runs after the copy, at insert time.
    if target.amends_id is not None:
        return
    if target.due_date_original is None and target.due_date is not None:
        target.due_date_original = target.due_date
    if target.due_date_effective is None:
        target.due_date_effective = target.due_date_original


def _require_override_reason(target: AdvancePayment) -> None:
    if target.due_date_effective == target.due_date_original:
        return
    reason = target.due_date_override_reason
    if reason is None or not reason.strip():
        raise ValueError("נדרש נימוק לשינוי מועד אפקטיבי")


def _ensure_original_immutable(target: AdvancePayment) -> None:
    history = inspect(target).attrs.due_date_original.history
    if not history.has_changes():
        return
    old_value = history.deleted[0] if history.deleted else None
    new_value = history.added[0] if history.added else None
    if old_value is not None and new_value != old_value:
        raise ValueError("לא ניתן לשנות מועד מקורי לאחר שנקבע")


@event.listens_for(AdvancePayment.due_date_original, "set", active_history=True)
def _load_original_history(target, value, _oldvalue, _initiator):
    return value


@event.listens_for(AdvancePayment, "before_insert")
def _before_insert(_mapper, _connection, target: AdvancePayment) -> None:
    _default_due_date_snapshots(target)
    _require_override_reason(target)


@event.listens_for(AdvancePayment, "before_update")
def _before_update(_mapper, _connection, target: AdvancePayment) -> None:
    _ensure_original_immutable(target)
    _default_due_date_snapshots(target)
    _require_override_reason(target)
