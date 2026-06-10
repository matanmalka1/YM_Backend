"""Work item creation and material intake flows."""

import json

from app.clients.enums import ClientStatus
from app.common.enums import ObligationType, VatType
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.tax_calendar.services.materialization_service import (
    TaxCalendarMaterializationService,
)
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.services.client_context_service import VatClientContextService
from app.vat.services.constants import (
    ACTION_MATERIAL_RECEIVED,
    ACTION_STATUS_CHANGED,
    ACTION_WORK_ITEM_CREATED_PENDING,
)
from app.vat.services.messages import (
    VAT_CLIENT_CLOSED_CREATE_ITEM,
    VAT_CLIENT_EXEMPT,
    VAT_CLIENT_FROZEN_CREATE_ITEM,
    VAT_INVALID_BIMONTHLY_PERIOD,
    VAT_ITEM_NOT_FOUND,
    VAT_MATERIALS_COMPLETE_INVALID_STATUS,
    VAT_PENDING_MATERIALS_NOTE_REQUIRED,
    VAT_WORK_ITEM_CONFLICT,
)
from app.vat.services.vat_type_resolver import resolve_effective_vat_type

_VAT_PERIOD_MONTHS_COUNT = {VatType.MONTHLY: 1, VatType.BIMONTHLY: 2}


def _validate_period_for_vat_type(period: str, vat_type: VatType) -> None:
    if vat_type == VatType.EXEMPT:
        raise AppError(
            VAT_CLIENT_EXEMPT,
            "VAT.CLIENT_EXEMPT",
        )
    if vat_type == VatType.BIMONTHLY:
        month = int(period.split("-")[1])
        if month % 2 == 0:
            raise AppError(
                VAT_INVALID_BIMONTHLY_PERIOD.format(period=period),
                "VAT.INVALID_PERIOD_FOR_FREQUENCY",
            )


def create_work_item(
    work_item_repo: VatWorkItemRepository,
    db,
    *,
    client_record_id: int,
    period: str,
    created_by: int,
    assigned_to: int | None = None,
    mark_pending: bool = False,
    pending_materials_note: str | None = None,
):
    client_record, legal_entity = VatClientContextService(db).get_active_client_and_entity(
        client_record_id
    )
    if client_record.status == ClientStatus.CLOSED:
        raise AppError(VAT_CLIENT_CLOSED_CREATE_ITEM, "VAT.CLIENT_CLOSED")
    if client_record.status == ClientStatus.FROZEN:
        raise AppError(VAT_CLIENT_FROZEN_CREATE_ITEM, "VAT.CLIENT_FROZEN")
    effective_vat_type = resolve_effective_vat_type(legal_entity)
    _validate_period_for_vat_type(period, effective_vat_type)

    # WARNING: This check only filters for non-deleted items (deleted_at IS NULL).
    # If we ever allow soft-deleting FILED items, this guard must be updated to
    # also block creation when a FILED item exists for the same period, even if deleted.
    existing = work_item_repo.get_by_client_record_period(client_record_id, period)
    if existing:
        raise ConflictError(
            VAT_WORK_ITEM_CONFLICT.format(client_record_id=client_record_id, period=period),
            "VAT.CONFLICT",
        )

    if mark_pending:
        if not pending_materials_note:
            raise AppError(
                VAT_PENDING_MATERIALS_NOTE_REQUIRED,
                "VAT.PENDING_NOTE_REQUIRED",
            )
        status = VatWorkItemStatus.PENDING_MATERIALS
    else:
        status = VatWorkItemStatus.MATERIAL_RECEIVED

    materializer = TaxCalendarMaterializationService(db)
    tax_calendar_entry = materializer.ensure_periodic_entry(
        ObligationType.VAT,
        period,
        _VAT_PERIOD_MONTHS_COUNT[effective_vat_type],
    )

    item = work_item_repo.create(
        client_record_id=client_record_id,
        period=period,
        period_type=effective_vat_type,
        created_by=created_by,
        status=status,
        pending_materials_note=pending_materials_note,
        assigned_to=assigned_to,
        tax_calendar_entry_id=tax_calendar_entry.id,
        due_date_original=tax_calendar_entry.due_date,
        due_date_effective=tax_calendar_entry.due_date,
    )
    materializer.link_vat_work_item(item)
    db.flush()

    action = ACTION_WORK_ITEM_CREATED_PENDING if mark_pending else ACTION_MATERIAL_RECEIVED
    work_item_repo.append_audit(
        work_item_id=item.id,
        performed_by=created_by,
        action=action,
        new_value=json.dumps({"status": status.value, "period": period}),
    )

    return item


def mark_materials_complete(
    work_item_repo: VatWorkItemRepository,
    *,
    item_id: int,
    performed_by: int,
):
    item = work_item_repo.get_by_id_for_update(item_id)
    if not item:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), "VAT.NOT_FOUND")

    if item.status != VatWorkItemStatus.PENDING_MATERIALS:
        raise AppError(
            VAT_MATERIALS_COMPLETE_INVALID_STATUS.format(status=item.status.value),
            "VAT.INVALID_TRANSITION",
        )

    old_status = item.status.value
    updated = work_item_repo.update_status(
        item_id,
        VatWorkItemStatus.MATERIAL_RECEIVED,
        item=item,
        pending_materials_note=None,
    )

    work_item_repo.append_audit(
        work_item_id=item_id,
        performed_by=performed_by,
        action=ACTION_STATUS_CHANGED,
        old_value=old_status,
        new_value=VatWorkItemStatus.MATERIAL_RECEIVED.value,
    )

    return updated
