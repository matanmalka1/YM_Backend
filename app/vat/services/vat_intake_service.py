"""Work item creation and material intake flows."""

from app.audit.audit_constants import (
    ACTION_VAT_WORK_ITEM_CREATED,
    ENTITY_VAT_WORK_ITEM,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.common.enums import ObligationType, VatType
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.tax_calendar.services.tax_calendar_materialization_service import (
    TaxCalendarMaterializationService,
)
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.services.vat_client_context_service import VatClientContextService
from app.vat.vat_audit import work_item_metadata
from app.vat.vat_messages import (
    VAT_CLIENT_EXEMPT,
    VAT_INVALID_BIMONTHLY_PERIOD,
    VAT_ITEM_NOT_FOUND,
    VAT_MATERIALS_COMPLETE_INVALID_STATUS,
    VAT_PENDING_MATERIALS_NOTE_REQUIRED,
    VAT_WORK_ITEM_CONFLICT,
)
from app.vat.vat_type_resolver import resolve_effective_vat_type

_VAT_PERIOD_MONTHS_COUNT = {VatType.MONTHLY: 1, VatType.BIMONTHLY: 2}


def _validate_period_for_vat_type(period: str, vat_type: VatType) -> None:
    if vat_type == VatType.EXEMPT:
        raise AppError(
            VAT_CLIENT_EXEMPT,
            ErrorCode.VAT_CLIENT_EXEMPT,
        )
    if vat_type == VatType.BIMONTHLY:
        month = int(period.split("-")[1])
        if month % 2 == 0:
            raise AppError(
                VAT_INVALID_BIMONTHLY_PERIOD.format(period=period),
                ErrorCode.VAT_INVALID_PERIOD_FOR_FREQUENCY,
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
    actor_display_name: str | None = None,
):
    # get_active_client_and_entity already applies the shared client-eligibility guard
    # (assert_client_record_is_active), which raises for CLOSED and FROZEN. A second
    # check here used to re-raise with VAT-local codes and was unreachable.
    _, legal_entity = VatClientContextService(db).get_active_client_and_entity(client_record_id)
    effective_vat_type = resolve_effective_vat_type(legal_entity)
    _validate_period_for_vat_type(period, effective_vat_type)

    # WARNING: This check only filters for non-deleted items (deleted_at IS NULL).
    # If we ever allow soft-deleting FILED items, this guard must be updated to
    # also block creation when a FILED item exists for the same period, even if deleted.
    existing = work_item_repo.get_by_client_record_period(client_record_id, period)
    if existing:
        raise ConflictError(
            VAT_WORK_ITEM_CONFLICT.format(client_record_id=client_record_id, period=period),
            ErrorCode.VAT_CONFLICT,
        )

    if mark_pending:
        if not pending_materials_note:
            raise AppError(
                VAT_PENDING_MATERIALS_NOTE_REQUIRED,
                ErrorCode.VAT_PENDING_NOTE_REQUIRED,
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

    EntityAuditWriter(db).record_action(
        ENTITY_VAT_WORK_ITEM,
        item.id,
        created_by,
        ACTION_VAT_WORK_ITEM_CREATED,
        new_value={"status": status.value, "period": period},
        actor_display_name=actor_display_name,
        metadata_json=work_item_metadata(item),
    )

    return item


def mark_materials_complete(
    work_item_repo: VatWorkItemRepository,
    *,
    item_id: int,
    performed_by: int,
    actor_display_name: str | None = None,
):
    item = work_item_repo.get_by_id_for_update(item_id)
    if not item:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)

    if item.status != VatWorkItemStatus.PENDING_MATERIALS:
        raise AppError(
            VAT_MATERIALS_COMPLETE_INVALID_STATUS.format(status=item.status.value),
            ErrorCode.VAT_INVALID_TRANSITION,
        )

    old_status = item.status.value
    updated = work_item_repo.update_status(
        item_id,
        VatWorkItemStatus.MATERIAL_RECEIVED,
        item=item,
        pending_materials_note=None,
    )

    EntityAuditWriter(work_item_repo.db).record_status_change(
        ENTITY_VAT_WORK_ITEM,
        item_id,
        performed_by,
        old_status,
        VatWorkItemStatus.MATERIAL_RECEIVED.value,
        actor_display_name=actor_display_name,
        metadata_json=work_item_metadata(item),
    )

    return updated
