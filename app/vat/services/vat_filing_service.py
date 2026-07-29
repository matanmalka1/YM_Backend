"""Advisor review and filing flows."""

from app.audit.audit_constants import (
    ACTION_VAT_WORK_ITEM_AMOUNT_OVERRIDDEN,
    ACTION_VAT_WORK_ITEM_FILED,
    ENTITY_VAT_WORK_ITEM,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.common.enums import ObligationStatus, SubmissionMethod
from app.common.obligation_closing import CLOSING_ASSIGNEE_REQUIRED_ISSUE
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, NotFoundError
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.schemas.vat_report import VatClosingReadinessResponse
from app.vat.vat_audit import work_item_metadata
from app.vat.vat_data_entry_common import assert_transition_allowed
from app.vat.vat_messages import (
    FINAL_VAT_AMOUNT_REQUIRED,
    OVERRIDE_JUSTIFICATION_REQUIRED,
    VAT_ASSIGNEE_REQUIRED,
    VAT_ITEM_NOT_FOUND,
)


def get_closing_readiness(
    work_item_repo: VatWorkItemRepository,
    *,
    item_id: int,
) -> VatClosingReadinessResponse:
    """The shared "can this be closed, and what is missing" gate (§4.1.8).

    Mirrors exactly what :func:`file_vat_return` enforces — assignee (D-15) and a
    final amount. An override supplied at filing time satisfies the amount gate,
    so its absence here is advisory, not a hard block.
    """
    item = work_item_repo.get_by_id(item_id)
    if not item:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)

    issues: list[str] = []
    if item.assigned_to is None:
        issues.append(CLOSING_ASSIGNEE_REQUIRED_ISSUE)
    if item.net_vat is None:
        issues.append(FINAL_VAT_AMOUNT_REQUIRED)

    return VatClosingReadinessResponse(
        work_item_id=item_id,
        is_ready=not issues,
        issues=issues,
    )


def file_vat_return(
    work_item_repo: VatWorkItemRepository,
    *,
    item_id: int,
    closed_by: int,
    submission_method: SubmissionMethod,
    override_amount: float | None = None,
    override_justification: str | None = None,
    submission_reference: str | None = None,
    actor_display_name: str | None = None,
):
    item = work_item_repo.get_by_id_for_update(item_id)
    if not item:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)

    assert_transition_allowed(item, ObligationStatus.SUBMITTED)

    if item.assigned_to is None:
        raise AppError(VAT_ASSIGNEE_REQUIRED, code=ErrorCode.VAT_ASSIGNEE_REQUIRED, status_code=400)

    is_overridden = override_amount is not None

    if is_overridden and not override_justification:
        raise AppError(OVERRIDE_JUSTIFICATION_REQUIRED, ErrorCode.VAT_JUSTIFICATION_REQUIRED)

    if item.net_vat is None and override_amount is None:
        raise AppError(
            FINAL_VAT_AMOUNT_REQUIRED, code=ErrorCode.VAT_MISSING_FINAL_AMOUNT, status_code=400
        )

    writer = EntityAuditWriter(work_item_repo.db)

    if is_overridden:
        final_amount = override_amount
        writer.record_action(
            ENTITY_VAT_WORK_ITEM,
            item_id,
            closed_by,
            ACTION_VAT_WORK_ITEM_AMOUNT_OVERRIDDEN,
            old_value={"final_vat_amount": str(item.net_vat)},
            new_value={"final_vat_amount": str(override_amount)},
            note=override_justification,
            actor_display_name=actor_display_name,
            metadata_json=work_item_metadata(item),
        )
    else:
        final_amount = float(item.net_vat)

    filed_item = work_item_repo.mark_filed(
        item_id=item_id,
        final_vat_amount=final_amount,
        submission_method=submission_method,
        closed_by=closed_by,
        is_overridden=is_overridden,
        override_justification=override_justification if is_overridden else None,
        submission_reference=submission_reference,
        item=item,
    )

    writer.record_action(
        ENTITY_VAT_WORK_ITEM,
        item_id,
        closed_by,
        ACTION_VAT_WORK_ITEM_FILED,
        new_value={
            "final_vat_amount": str(final_amount),
            "submission_method": submission_method.value,
            "is_overridden": is_overridden,
            "closed_late": item.closed_late,
        },
        actor_display_name=actor_display_name,
        metadata_json=work_item_metadata(item),
    )

    return filed_item
