"""Operational metadata mutations for VAT work items."""

from app.audit.audit_constants import ENTITY_VAT_WORK_ITEM
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.common.enums import ObligationStatus
from app.common.obligation_chain import assert_deletable
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, NotFoundError
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.vat_audit import work_item_metadata
from app.vat.vat_messages import (
    VAT_FILED_ITEM_IMMUTABLE,
    VAT_ITEM_NOT_FOUND,
)

_UPDATEABLE_FIELDS = {"assigned_to", "pending_materials_note"}


def update_work_item_metadata(
    work_item_repo: VatWorkItemRepository,
    *,
    item_id: int,
    performed_by: int,
    patch: dict,
    actor_display_name: str | None = None,
):
    item = work_item_repo.get_by_id_for_update(item_id)
    if not item:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)
    if item.status == ObligationStatus.SUBMITTED:
        raise AppError(VAT_FILED_ITEM_IMMUTABLE, ErrorCode.VAT_FILED_IMMUTABLE)

    fields = {key: value for key, value in patch.items() if key in _UPDATEABLE_FIELDS}
    old_values = {key: getattr(item, key) for key in fields}
    changed = {key: value for key, value in fields.items() if old_values[key] != value}

    updated = work_item_repo.update_work_item_metadata(item_id, item=item, **fields)

    if changed:
        EntityAuditWriter(work_item_repo.db).record_update(
            ENTITY_VAT_WORK_ITEM,
            item_id,
            performed_by,
            old_value={key: old_values[key] for key in changed},
            new_value=dict(changed),
            actor_display_name=actor_display_name,
            metadata_json=work_item_metadata(item),
        )

    return updated


def soft_delete_work_item(
    work_item_repo: VatWorkItemRepository,
    *,
    item_id: int,
    deleted_by: int,
    actor_display_name: str | None = None,
) -> None:
    item = work_item_repo.get_by_id_for_update(item_id)
    if not item:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)
    if item.status == ObligationStatus.SUBMITTED:
        raise AppError(VAT_FILED_ITEM_IMMUTABLE, ErrorCode.VAT_FILED_IMMUTABLE)
    assert_deletable(item)

    metadata = work_item_metadata(item)
    status_before = item.status.value
    work_item_repo.soft_delete_work_item(item_id, deleted_by=deleted_by, item=item)
    EntityAuditWriter(work_item_repo.db).record_delete(
        ENTITY_VAT_WORK_ITEM,
        item_id,
        deleted_by,
        old_value={"status": status_before},
        actor_display_name=actor_display_name,
        metadata_json=metadata,
    )
