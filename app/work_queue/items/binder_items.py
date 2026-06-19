from __future__ import annotations

from app.binders.repositories.binder_repository import BinderRepository
from app.work_queue.schemas.work_queue import (
    WorkQueueItem,
    WorkQueueSourceType,
    WorkQueueUrgency,
)
from app.work_queue.items.common import WorkQueueContext

_STALE_HANDOVER_THRESHOLD_DAYS = 30


def binder_items(ctx: WorkQueueContext) -> list[WorkQueueItem]:
    """Return work-queue items for binders that have been ready for handover too long."""
    binders = BinderRepository(ctx.db).list_overdue_handover(
        overdue_days=_STALE_HANDOVER_THRESHOLD_DAYS
    )
    ctx.preload_client_identities(binder.client_record_id for binder in binders)
    items = []
    for binder in binders:
        ready_at = binder.ready_for_handover_at
        if ready_at is None:
            continue
        ready_date = ready_at.date() if hasattr(ready_at, "date") else ready_at
        days_waiting = (ctx.today - ready_date).days
        items.append(
            ctx.item(
                WorkQueueSourceType.BINDER,
                binder.id,
                f"קלסר {binder.binder_number} — ממתין למסירה {days_waiting} ימים",
                ready_date,
                binder.client_record_id,
                item_urgency=WorkQueueUrgency.OVERDUE,
                status_label=binder.location_status.value
                if hasattr(binder.location_status, "value")
                else str(binder.location_status),
            )
        )
    return items
