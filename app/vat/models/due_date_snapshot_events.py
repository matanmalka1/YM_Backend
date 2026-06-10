"""SQLAlchemy events for VAT work item due-date snapshots."""
# pylint: disable=duplicate-code  # parallel logic in advance_payments.models.due_date_snapshot_events

from sqlalchemy import event, inspect

from app.vat.models.vat_work_item import VatWorkItem


def _default_due_date_snapshots(target: VatWorkItem) -> None:
    if target.due_date_original is not None and target.due_date_effective is None:
        target.due_date_effective = target.due_date_original


def _require_override_reason(target: VatWorkItem) -> None:
    if target.due_date_effective == target.due_date_original:
        return
    reason = target.due_date_override_reason
    if reason is None or not reason.strip():
        raise ValueError("נדרש נימוק לשינוי מועד אפקטיבי")


def _ensure_original_immutable(target: VatWorkItem) -> None:
    history = inspect(target).attrs.due_date_original.history
    if not history.has_changes():
        return
    old_value = history.deleted[0] if history.deleted else None
    new_value = history.added[0] if history.added else None
    if old_value is not None and new_value != old_value:
        raise ValueError("לא ניתן לשנות מועד מקורי לאחר שנקבע")


@event.listens_for(VatWorkItem.due_date_original, "set", active_history=True)
def _load_original_history(target, value, _oldvalue, _initiator):
    return value


@event.listens_for(VatWorkItem, "before_insert")
def _before_insert(_mapper, _connection, target: VatWorkItem) -> None:
    _default_due_date_snapshots(target)
    _require_override_reason(target)


@event.listens_for(VatWorkItem, "before_update")
def _before_update(_mapper, _connection, target: VatWorkItem) -> None:
    _ensure_original_immutable(target)
    _default_due_date_snapshots(target)
    _require_override_reason(target)
