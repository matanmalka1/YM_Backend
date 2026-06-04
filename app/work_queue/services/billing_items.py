from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.advance_payments.models.advance_payment import (
    AdvancePayment,
    AdvancePaymentStatus,
)
from app.charge.models.charge import Charge, ChargeStatus
from app.charge.services.constants import UNPAID_CHARGE_TASK_THRESHOLD_DAYS
from app.clients.repositories.active_client_scope import scope_to_active_clients_stmt
from app.work_queue.schemas.work_queue import (
    WorkQueueItem,
    WorkQueueSourceType,
    WorkQueueUrgency,
)
from app.work_queue.services.common import UPCOMING_WINDOW_DAYS, WorkQueueContext
from app.work_queue.services.metadata import (
    advance_payment_metadata,
    charge_metadata,
)


def advance_payment_items(
    ctx: WorkQueueContext, client_record_id: int | None
) -> list[WorkQueueItem]:
    cutoff = ctx.today + timedelta(days=UPCOMING_WINDOW_DAYS)
    stmt = scope_to_active_clients_stmt(select(AdvancePayment), AdvancePayment).where(
        AdvancePayment.deleted_at.is_(None),
        AdvancePayment.status.in_([AdvancePaymentStatus.PENDING, AdvancePaymentStatus.PARTIAL]),
        (AdvancePayment.due_date_effective <= cutoff) | (AdvancePayment.due_date_effective.is_(None) & (AdvancePayment.due_date <= cutoff)),
    )
    if client_record_id is not None:
        stmt = stmt.where(AdvancePayment.client_record_id == client_record_id)
    payments = list(ctx.db.scalars(stmt))
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
    stmt = scope_to_active_clients_stmt(select(Charge), Charge).where(
        Charge.deleted_at.is_(None),
        Charge.status == ChargeStatus.ISSUED,
        Charge.issued_at.isnot(None),
        Charge.issued_at <= threshold,
    )
    if client_record_id is not None:
        stmt = stmt.where(Charge.client_record_id == client_record_id)
    if business_id is not None:
        stmt = stmt.where(Charge.business_id == business_id)
    charges = list(ctx.db.scalars(stmt))
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
