"""Advisor review and filing flows."""

import json

from app.common.enums import SubmissionMethod
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, NotFoundError
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.vat_constants import ACTION_FILED, ACTION_OVERRIDE
from app.vat.vat_data_entry_common import assert_transition_allowed
from app.vat.vat_messages import (
    AMENDED_ITEM_NOT_FILED,
    AMENDED_ITEM_NOT_FOUND,
    AMENDED_ITEM_WRONG_CLIENT,
    AMENDMENT_CYCLE_DETECTED,
    FINAL_VAT_AMOUNT_REQUIRED,
    OVERRIDE_JUSTIFICATION_REQUIRED,
    VAT_AMENDMENT_ID_REQUIRED,
    VAT_ASSIGNEE_REQUIRED,
    VAT_ITEM_NOT_FOUND,
)


def _validate_amendment(
    work_item_repo: VatWorkItemRepository,
    item,
    amends_item_id: int,
) -> None:
    amended_item = work_item_repo.get_by_id(amends_item_id)
    if amended_item is None:
        raise AppError(
            AMENDED_ITEM_NOT_FOUND, code=ErrorCode.VAT_AMENDED_ITEM_NOT_FOUND, status_code=404
        )
    if amended_item.client_record_id != item.client_record_id:
        raise AppError(
            AMENDED_ITEM_WRONG_CLIENT, code=ErrorCode.VAT_AMENDED_ITEM_WRONG_CLIENT, status_code=400
        )
    if amended_item.status != VatWorkItemStatus.FILED:
        raise AppError(
            AMENDED_ITEM_NOT_FILED, code=ErrorCode.VAT_AMENDED_ITEM_NOT_FILED, status_code=400
        )

    current_item = amended_item
    while current_item is not None:
        if current_item.id == item.id:
            raise AppError(
                AMENDMENT_CYCLE_DETECTED, code=ErrorCode.VAT_AMENDMENT_CYCLE, status_code=400
            )
        if current_item.amends_item_id is None:
            break
        current_item = work_item_repo.get_by_id(current_item.amends_item_id)


def file_vat_return(
    work_item_repo: VatWorkItemRepository,
    *,
    item_id: int,
    filed_by: int,
    submission_method: SubmissionMethod,
    override_amount: float | None = None,
    override_justification: str | None = None,
    submission_reference: str | None = None,
    is_amendment: bool = False,
    amends_item_id: int | None = None,
):
    item = work_item_repo.get_by_id_for_update(item_id)
    if not item:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)

    assert_transition_allowed(item, VatWorkItemStatus.FILED)

    if item.assigned_to is None:
        raise AppError(VAT_ASSIGNEE_REQUIRED, code=ErrorCode.VAT_ASSIGNEE_REQUIRED, status_code=400)

    if is_amendment and amends_item_id is None:
        raise AppError(
            VAT_AMENDMENT_ID_REQUIRED, code=ErrorCode.VAT_AMENDMENT_ID_REQUIRED, status_code=400
        )

    if amends_item_id is not None:
        _validate_amendment(work_item_repo, item, amends_item_id)

    is_overridden = override_amount is not None

    if is_overridden and not override_justification:
        raise AppError(OVERRIDE_JUSTIFICATION_REQUIRED, ErrorCode.VAT_JUSTIFICATION_REQUIRED)

    if item.net_vat is None and override_amount is None:
        raise AppError(
            FINAL_VAT_AMOUNT_REQUIRED, code=ErrorCode.VAT_MISSING_FINAL_AMOUNT, status_code=400
        )

    if is_overridden:
        final_amount = override_amount
        work_item_repo.append_audit(
            work_item_id=item_id,
            performed_by=filed_by,
            action=ACTION_OVERRIDE,
            old_value=str(item.net_vat),
            new_value=str(override_amount),
            note=override_justification,
        )
    else:
        final_amount = float(item.net_vat)

    filed_item = work_item_repo.mark_filed(
        item_id=item_id,
        final_vat_amount=final_amount,
        submission_method=submission_method,
        filed_by=filed_by,
        is_overridden=is_overridden,
        override_justification=override_justification if is_overridden else None,
        submission_reference=submission_reference,
        is_amendment=is_amendment,
        amends_item_id=amends_item_id,
        item=item,
    )

    work_item_repo.append_audit(
        work_item_id=item_id,
        performed_by=filed_by,
        action=ACTION_FILED,
        performed_at=filed_item.filed_at,
        new_value=json.dumps(
            {
                "final_vat_amount": str(final_amount),
                "submission_method": submission_method.value,
                "is_overridden": is_overridden,
            }
        ),
    )

    return filed_item
