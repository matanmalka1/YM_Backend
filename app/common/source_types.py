from __future__ import annotations

from enum import Enum as PyEnum

from app.common.entity_links import LinkedEntity, entity_route


class WorkQueueSourceType(str, PyEnum):
    VAT_WORK_ITEM = "vat_work_item"
    ANNUAL_REPORT = "annual_report"
    ADVANCE_PAYMENT = "advance_payment"
    CHARGE = "charge"
    BINDER = "binder"
    TASK = "task"


def normalize_source_domain(value: str | None) -> WorkQueueSourceType | None:
    if not value:
        return None
    try:
        return WorkQueueSourceType(value)
    except ValueError:
        return None


def source_route(source_type: WorkQueueSourceType, source_id: int) -> str | None:
    """Route for a queue row's source entity.

    URL strings come from `entity_links`. Two source types deliberately diverge from
    the canonical entity link: a queue row has no owning-client context, so an advance
    payment falls back to its unscoped list, and a task needs no link at all because
    the queue row is the task and is acted on in place.
    """
    if source_type == WorkQueueSourceType.ADVANCE_PAYMENT:
        return "/tax/advance-payments"
    if source_type == WorkQueueSourceType.TASK:
        return None
    return entity_route(LinkedEntity(source_type.value), source_id)


__all__ = ["WorkQueueSourceType", "normalize_source_domain", "source_route"]
