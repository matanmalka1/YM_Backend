from __future__ import annotations

from datetime import timedelta

from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.charges.charge_constants import UNPAID_CHARGE_TASK_THRESHOLD_DAYS
from app.charges.repositories.charge_repository import ChargeRepository
from app.work_queue.items.common import UPCOMING_WINDOW_DAYS, WorkQueueContext
from app.work_queue.schemas.work_queue import (
    WorkQueueItem,
    WorkQueueSourceType,
    WorkQueueUrgency,
)
from app.work_queue.work_queue_metadata import (
    advance_payment_metadata,
    charge_metadata,
)


def advance_payment_items(
    ctx: WorkQueueContext, client_record_id: int | None
) -> list[WorkQueueItem]:
    cutoff = ctx.today + timedelta(days=UPCOMING_WINDOW_DAYS)
    payments = AdvancePaymentRepository(ctx.db).list_due_for_work_queue(cutoff, client_record_id)
    ctx.preload_client_identities(payment.client_record_id for payment in payments)
    items: list[WorkQueueItem] = []
    for payment in payments:
        effective_due_date = payment.due_date_effective or payment.due_date
        metadata = advance_payment_metadata(payment)
        items.append(
            ctx.item(
                WorkQueueSourceType.ADVANCE_PAYMENT,
                payment.id,
                f"מקדמה: {metadata['period_label']}",
                effective_due_date,
                payment.client_record_id,
                status_label=payment.status.value
                if hasattr(payment.status, "value")
                else str(payment.status),
                metadata=metadata,
            )
        )
    return items


def charge_items(
    ctx: WorkQueueContext,
    client_record_id: int | None,
    business_id: int | None,
) -> list[WorkQueueItem]:
    threshold = ctx.today - timedelta(days=UNPAID_CHARGE_TASK_THRESHOLD_DAYS)
    charges = ChargeRepository(ctx.db).list_unpaid_for_work_queue(
        threshold, client_record_id, business_id
    )
    ctx.preload_client_identities(charge.client_record_id for charge in charges)
    return [_charge_item(ctx, charge) for charge in charges]


def _charge_item(ctx: WorkQueueContext, charge) -> WorkQueueItem:
    due_date = charge.issued_at.date() + timedelta(days=UNPAID_CHARGE_TASK_THRESHOLD_DAYS)
    return ctx.item(
        WorkQueueSourceType.CHARGE,
        charge.id,
        "חיוב לא שולם",
        due_date,
        charge.client_record_id,
        business_id=charge.business_id,
        # Always OVERDUE: items only appear after the unpaid threshold has passed.
        item_urgency=WorkQueueUrgency.OVERDUE,
        status_label=charge.status.value if hasattr(charge.status, "value") else str(charge.status),
        metadata=charge_metadata(charge, due_date),
    )
