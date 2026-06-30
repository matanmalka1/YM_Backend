"""Invoice delete flow for VAT work items."""

from app.audit.audit_constants import ACTION_VAT_INVOICE_DELETED, ENTITY_VAT_INVOICE
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.vat.repositories.vat_invoice_repository import VatInvoiceRepository
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.vat_audit import invoice_metadata, invoice_snapshot
from app.vat.vat_data_entry_common import (
    assert_editable,
    recalculate_totals,
)
from app.vat.vat_messages import (
    VAT_INVOICE_NOT_FOUND_IN_WORK_ITEM,
    VAT_ITEM_NOT_FOUND,
)


def delete_invoice(
    work_item_repo: VatWorkItemRepository,
    invoice_repo: VatInvoiceRepository,
    *,
    item_id: int,
    invoice_id: int,
    performed_by: int,
    actor_display_name: str | None = None,
):
    """
    Delete an invoice from a work item.

    Rules:
    - Work item must not be FILED.
    - Invoice must belong to this work item.
    """
    item = work_item_repo.get_by_id(item_id)
    if not item:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)

    assert_editable(item)

    invoice = invoice_repo.get_by_id(invoice_id)
    if not invoice or invoice.work_item_id != item_id:
        raise NotFoundError(
            VAT_INVOICE_NOT_FOUND_IN_WORK_ITEM.format(invoice_id=invoice_id, item_id=item_id),
            ErrorCode.VAT_NOT_FOUND,
        )

    snapshot = invoice_snapshot(invoice)
    metadata = invoice_metadata(
        item, invoice_number=invoice.invoice_number, business_id=invoice.business_activity_id
    )

    deleted = invoice_repo.delete(invoice_id)
    if deleted:
        recalculate_totals(work_item_repo, invoice_repo, item_id)
        EntityAuditWriter(work_item_repo.db).record_action(
            ENTITY_VAT_INVOICE,
            invoice_id,
            performed_by,
            ACTION_VAT_INVOICE_DELETED,
            old_value=snapshot,
            actor_display_name=actor_display_name,
            metadata_json=metadata,
        )

    return deleted
