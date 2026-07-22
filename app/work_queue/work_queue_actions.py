from __future__ import annotations

from app.core.action_builders import link_action as _link
from app.core.action_builders import modal_action as _modal
from app.core.action_builders import mutation_action as _mutation
from app.core.action_schemas import ActionDescriptor
from app.tasks.models.task import TaskStatus
from app.work_queue.items.common import source_route
from app.work_queue.schemas.work_queue import WorkQueueSourceType


def _disabled(action: ActionDescriptor, reason: str) -> ActionDescriptor:
    action.disabled = True
    action.disabled_reason = reason
    return action


def source_link_action(
    source_type: WorkQueueSourceType, source_id: int, client_record_id: int | None = None
) -> ActionDescriptor | None:
    route = source_route(source_type, source_id, client_record_id)
    if route is None:
        return None
    labels = {
        WorkQueueSourceType.VAT_WORK_ITEM: 'פתח דוח מע"מ',
        WorkQueueSourceType.ANNUAL_REPORT: "פתח דוח שנתי",
        WorkQueueSourceType.ADVANCE_PAYMENT: "פתח מקדמה",
        WorkQueueSourceType.CHARGE: "פתח חיוב",
        WorkQueueSourceType.BINDER: "פתח קלסר",
    }
    keys = {
        WorkQueueSourceType.VAT_WORK_ITEM: "open_vat_work_item",
        WorkQueueSourceType.ANNUAL_REPORT: "open_annual_report",
        WorkQueueSourceType.ADVANCE_PAYMENT: "open_advance_payment_context",
        WorkQueueSourceType.CHARGE: "open_charge_context",
        WorkQueueSourceType.BINDER: "open_binder_context",
    }
    key = keys.get(source_type)
    label = labels.get(source_type)
    if key is None or label is None:
        return None
    return _link(key, label, route, primary=True)


def task_actions(
    task_id: int,
    status: str,
    *,
    key_suffix: bool = False,
    include_open: bool = True,
    include_delete: bool = True,
    label_context: str | None = None,
) -> list[ActionDescriptor]:
    actions: list[ActionDescriptor] = []
    suffix = f"_{task_id}" if key_suffix else ""
    label_suffix = f": {label_context}" if label_context else ""
    if include_open:
        actions.append(
            _modal(
                f"continue_task{suffix}",
                f"פתח משימה{label_suffix}",
                task_id=task_id,
                primary=True,
            )
        )
    if status == TaskStatus.OPEN.value:
        actions.append(_modal(f"edit_task{suffix}", f"ערוך משימה{label_suffix}", task_id=task_id))
        actions.extend(
            [
                _mutation(
                    f"complete_task{suffix}",
                    f"סמן כהושלמה{label_suffix}",
                    task_id=task_id,
                    confirm_title="השלמת משימה",
                    confirm_message="האם לסמן את המשימה כהושלמה?",
                    variant="primary",
                ),
                _mutation(
                    f"cancel_task{suffix}",
                    f"בטל משימה{label_suffix}",
                    task_id=task_id,
                    confirm_title="ביטול משימה",
                    confirm_message="האם לבטל את המשימה?",
                    variant="danger",
                ),
            ]
        )
    else:
        reason = "המשימה כבר הושלמה" if status == TaskStatus.DONE.value else "המשימה כבר בוטלה"
        actions.extend(
            [
                _disabled(
                    _modal(
                        f"edit_task{suffix}",
                        f"ערוך משימה{label_suffix}",
                        task_id=task_id,
                    ),
                    reason,
                ),
                _disabled(
                    _mutation(
                        f"complete_task{suffix}",
                        f"סמן כהושלמה{label_suffix}",
                        task_id=task_id,
                        variant="primary",
                    ),
                    reason,
                ),
                _disabled(
                    _mutation(
                        f"cancel_task{suffix}",
                        f"בטל משימה{label_suffix}",
                        task_id=task_id,
                        variant="danger",
                    ),
                    reason,
                ),
            ]
        )
    if include_delete:
        actions.append(
            _mutation(
                f"delete_task{suffix}",
                f"מחק משימה{label_suffix}",
                task_id=task_id,
                confirm_title="מחיקת משימה",
                confirm_message="האם למחוק את המשימה? המחיקה לא תשפיע על מקור המערכת.",
                variant="danger",
            )
        )
    return actions


def create_linked_task_action() -> ActionDescriptor:
    return _modal("create_linked_task", "צור משימה")


def source_actions(
    source_type: WorkQueueSourceType,
    source_id: int,
    client_record_id: int | None = None,
) -> list[ActionDescriptor]:
    actions = []
    open_action = source_link_action(source_type, source_id, client_record_id)
    if open_action is not None:
        actions.append(open_action)
    if source_type != WorkQueueSourceType.TASK:
        actions.append(create_linked_task_action())
    return actions


__all__ = [
    "create_linked_task_action",
    "source_actions",
    "source_link_action",
    "task_actions",
]
