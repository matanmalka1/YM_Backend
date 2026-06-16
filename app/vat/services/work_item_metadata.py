"""Operational metadata mutations for VAT work items."""

from app.core.error_codes import ErrorCode
import json

from app.core.exceptions import AppError, NotFoundError
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.services.constants import (
    ACTION_METADATA_UPDATED,
    ACTION_WORK_ITEM_DELETED,
)
from app.vat.services.messages import (
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
):
    item = work_item_repo.get_by_id_for_update(item_id)
    if not item:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)
    if item.status == VatWorkItemStatus.FILED:
        raise AppError(VAT_FILED_ITEM_IMMUTABLE, ErrorCode.VAT_FILED_IMMUTABLE)

    fields = {key: value for key, value in patch.items() if key in _UPDATEABLE_FIELDS}
    old_values = {key: getattr(item, key) for key in fields}
    changed = {
        key: {"old": old_values[key], "new": value}
        for key, value in fields.items()
        if old_values[key] != value
    }

    updated = work_item_repo.update_work_item_metadata(item_id, item=item, **fields)

    for field, values in changed.items():
        work_item_repo.append_audit(
            work_item_id=item_id,
            performed_by=performed_by,
            action=ACTION_METADATA_UPDATED,
            old_value=json.dumps({field: values["old"]}, ensure_ascii=False),
            new_value=json.dumps({field: values["new"]}, ensure_ascii=False),
        )

    return updated


def soft_delete_work_item(
    work_item_repo: VatWorkItemRepository,
    *,
    item_id: int,
    deleted_by: int,
) -> None:
    item = work_item_repo.get_by_id_for_update(item_id)
    if not item:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)
    if item.status == VatWorkItemStatus.FILED:
        raise AppError(VAT_FILED_ITEM_IMMUTABLE, ErrorCode.VAT_FILED_IMMUTABLE)

    work_item_repo.soft_delete_work_item(item_id, deleted_by=deleted_by, item=item)
    work_item_repo.append_audit(
        work_item_id=item_id,
        performed_by=deleted_by,
        action=ACTION_WORK_ITEM_DELETED,
        old_value=json.dumps({"deleted_at": None, "deleted_by": None}, ensure_ascii=False),
        new_value=json.dumps({"deleted": True, "deleted_by": deleted_by}, ensure_ascii=False),
    )
