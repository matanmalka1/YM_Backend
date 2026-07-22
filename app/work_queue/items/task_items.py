from __future__ import annotations

from app.work_queue.items.common import (
    SOURCE_TYPE_LABELS,
    WorkQueueContext,
    display_status_label,
    urgency,
)
from app.work_queue.schemas.work_queue import (
    LinkedTaskSummary,
    WorkQueueItem,
    WorkQueueSourceType,
    WorkQueueUrgency,
)
from app.work_queue.work_queue_actions import task_actions


def task_summary(task, assigned_user_name: str | None = None) -> LinkedTaskSummary:
    due = task.due_date
    return LinkedTaskSummary(
        id=task.id,
        title=task.title,
        status=task.status.value,
        due_date=due,
        priority=task.priority.value if hasattr(task.priority, "value") else task.priority,
        assigned_user_id=task.assigned_to_user_id,
        assigned_user_name=assigned_user_name,
        assigned_role=task.assigned_role,
    )


def task_item(ctx: WorkQueueContext, task, assigned_user_name: str | None = None) -> WorkQueueItem:
    due = task.due_date
    item_urgency = urgency(due, ctx.today) if due is not None else WorkQueueUrgency.UPCOMING
    return WorkQueueItem(
        id=f"{WorkQueueSourceType.TASK.value}:{task.id}",
        source_type=WorkQueueSourceType.TASK,
        source_id=task.id,
        title=task.title,
        description=task.description,
        type_label=SOURCE_TYPE_LABELS[WorkQueueSourceType.TASK],
        status_label=display_status_label(WorkQueueSourceType.TASK, task.status.value),
        due_date=due,
        urgency=item_urgency,
        client_record_id=None,
        client_name=None,
        business_id=None,
        linked_tasks=[],
        linked_tasks_count=0,
        available_actions=task_actions(task.id, task.status.value),
        metadata={
            "status": task.status.value,
            "priority": task.priority.value,
            "description": task.description,
            "assigned_to_user_id": task.assigned_to_user_id,
            "assigned_to_user_name": assigned_user_name,
            "assigned_role": task.assigned_role,
            "action_key": task.action_key,
            "action_payload": task.action_payload,
            "source_domain": task.source_domain,
            "source_id": task.source_id,
        },
    )


__all__ = ["task_item", "task_summary"]
