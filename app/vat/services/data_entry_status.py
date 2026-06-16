"""Status transitions for VAT work items during data entry."""

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, NotFoundError
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.services.constants import ACTION_STATUS_CHANGED
from app.vat.services.data_entry_common import assert_transition_allowed
from app.vat.services.messages import (
    VAT_CORRECTION_NOTE_REQUIRED,
    VAT_ITEM_NOT_FOUND,
    VAT_READY_FOR_REVIEW_INVALID_STATUS,
)


def mark_ready_for_review(
    work_item_repo: VatWorkItemRepository,
    *,
    item_id: int,
    performed_by: int,
):
    """
    Transition DATA_ENTRY_IN_PROGRESS → READY_FOR_REVIEW.

    Raises:
        AppError: If not in DATA_ENTRY_IN_PROGRESS.
    """
    item = work_item_repo.get_by_id_for_update(item_id)
    if not item:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)

    if item.status != VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS:
        raise AppError(
            VAT_READY_FOR_REVIEW_INVALID_STATUS.format(status=item.status.value),
            ErrorCode.VAT_INVALID_TRANSITION,
        )

    updated = work_item_repo.update_status(item_id, VatWorkItemStatus.READY_FOR_REVIEW, item=item)

    work_item_repo.append_audit(
        work_item_id=item_id,
        performed_by=performed_by,
        action=ACTION_STATUS_CHANGED,
        old_value=VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS.value,
        new_value=VatWorkItemStatus.READY_FOR_REVIEW.value,
    )

    return updated


def send_back_for_correction(
    work_item_repo: VatWorkItemRepository,
    *,
    item_id: int,
    performed_by: int,
    correction_note: str,
):
    """
    Advisor sends work item back for correction.
    READY_FOR_REVIEW → DATA_ENTRY_IN_PROGRESS.

    Requires a non-empty correction note.
    """
    if not correction_note or not correction_note.strip():
        raise AppError(
            VAT_CORRECTION_NOTE_REQUIRED,
            ErrorCode.VAT_JUSTIFICATION_REQUIRED,
        )

    item = work_item_repo.get_by_id_for_update(item_id)
    if not item:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)

    assert_transition_allowed(item, VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS)

    updated = work_item_repo.update_status(
        item_id, VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS, item=item
    )

    work_item_repo.append_audit(
        work_item_id=item_id,
        performed_by=performed_by,
        action=ACTION_STATUS_CHANGED,
        old_value=VatWorkItemStatus.READY_FOR_REVIEW.value,
        new_value=VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS.value,
        note=correction_note,
    )

    return updated
