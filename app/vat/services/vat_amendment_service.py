"""Correcting a closed VAT period, by creating a second row for it (D-10, D-21).

VAT already carried the *fields* for this and could never reach them: the
amendment flag was set at filing time on a row that already existed, and a
second row for the same period could not be created at all — the active unique
index blocked it and a filed row could not be soft-deleted to free the slot. The
mechanism was unreachable, not merely unused (§4.1.6).

What replaces it: an explicit act on the closed record, which copies it whole —
figures and invoices — and opens the copy at ``in_progress``. Nothing is being
waited for, because the material already exists; only the numbers are wrong.
"""

from app.audit.audit_constants import (
    ACTION_VAT_WORK_ITEM_AMENDED,
    ACTION_VAT_WORK_ITEM_AMENDMENT_WITHDRAWN,
    ENTITY_VAT_WORK_ITEM,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.common.enums import ObligationStatus
from app.common.obligation_chain import (
    assert_amendable,
    assert_withdrawable,
    copy_for_amendment,
    select_chain,
    withdraw_amendment,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.vat.models.vat_work_item import VatWorkItem
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.vat_audit import work_item_metadata
from app.vat.vat_messages import VAT_ITEM_NOT_FOUND

#: The closing facts under VAT's own names. Same reason as ``closed_at``: the
#: amendment has not been filed, so it has not been filed by any method, under
#: any reference, at any overridden amount.
_VAT_CLOSING_FACTS = frozenset(
    {
        "submission_method",
        "submission_reference",
        "final_vat_amount",
        "is_overridden",
        "override_justification",
    }
)


def create_amendment(
    work_item_repo: VatWorkItemRepository,
    *,
    item_id: int,
    actor_id: int,
    actor_display_name: str | None = None,
) -> VatWorkItem:
    """Open a correction of a closed VAT period.

    The original is locked for update: two advisors pressing "amend" on the same
    period would otherwise both pass the gate and both insert, and only the
    unique index on ``amends_id`` would stop the second — as a 500, after the
    work of copying every invoice.
    """
    original = work_item_repo.get_by_id_for_update(item_id)
    if original is None:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)

    assert_amendable(original)

    amendment = work_item_repo.create_amendment(
        original,
        fields={
            **copy_for_amendment(original, also_exclude=_VAT_CLOSING_FACTS),
            # D-21: the material already exists, so nothing is being waited for.
            "status": ObligationStatus.IN_PROGRESS,
            "created_by": actor_id,
        },
    )

    EntityAuditWriter(work_item_repo.db).record_action(
        ENTITY_VAT_WORK_ITEM,
        amendment.id,
        actor_id,
        ACTION_VAT_WORK_ITEM_AMENDED,
        new_value={"amends_id": original.id, "period": amendment.period},
        actor_display_name=actor_display_name,
        metadata_json=work_item_metadata(amendment),
    )

    return amendment


def withdraw(
    work_item_repo: VatWorkItemRepository,
    *,
    item_id: int,
    actor_id: int,
    actor_display_name: str | None = None,
) -> VatWorkItem:
    """Take back an open correction and return the period to its filed record.

    Both rows are locked, and **the original first** — ascending id, since an
    amendment is always the younger row. ``create_amendment`` locks the original
    too, so a withdrawal and a correction racing on one period queue behind the
    same row instead of deadlocking on opposite orders. The gate is re-checked
    after the lock: without that, two withdrawals both pass it and the second
    revives an original that is already live.

    The copied invoices stay attached to the withdrawn row. That is the same state
    as any soft-deleted work item's invoices, and it is what makes the withdrawal
    readable afterwards: the correction's figures are still there to look at.

    Returns the original, not the amendment: it is the record the office works
    with from here.
    """
    requested = work_item_repo.get(item_id, include_deleted=False)
    if requested is None:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)
    assert_withdrawable(requested)

    original = work_item_repo.get_by_id_for_update(requested.amends_id)
    amendment = work_item_repo.get_by_id_for_update(item_id)
    if original is None or amendment is None:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)
    assert_withdrawable(amendment)

    status_before = amendment.status.value
    metadata = work_item_metadata(amendment)
    withdraw_amendment(amendment, original, actor_id=actor_id)
    work_item_repo.db.flush()

    EntityAuditWriter(work_item_repo.db).record_action(
        ENTITY_VAT_WORK_ITEM,
        amendment.id,
        actor_id,
        ACTION_VAT_WORK_ITEM_AMENDMENT_WITHDRAWN,
        old_value={"status": status_before, "amends_id": original.id},
        actor_display_name=actor_display_name,
        metadata_json={**metadata, "restored_original_id": original.id},
    )

    return original


def list_chain(work_item_repo: VatWorkItemRepository, *, item_id: int) -> list[VatWorkItem]:
    """Every record for this period, oldest first — the correction history.

    Resolved from the requested record rather than from the tip, so a link
    reached from an old audit entry or a stale link answers with the same chain.
    """
    item = work_item_repo.get(item_id, include_deleted=False)
    if item is None:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)
    return list(
        work_item_repo.db.scalars(
            select_chain(
                VatWorkItem,
                client_record_id=item.client_record_id,
                period_column=VatWorkItem.period,
                period_value=item.period,
            )
        ).all()
    )
