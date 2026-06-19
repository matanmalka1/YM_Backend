"""Invoice update flow for VAT work items."""

from decimal import Decimal

from app.businesses.repositories.business_repository import BusinessRepository
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.vat.integrations.tax_rules_financials import (
    get_financial_value,
    get_vat_deduction_rate_for_category,
)
from app.vat.repositories.vat_invoice_repository import VatInvoiceRepository
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.schemas.vat_invoice_schema import validate_counterparty_pair
from app.vat.vat_constants import ACTION_INVOICE_UPDATED
from app.vat.vat_data_entry_common import (
    assert_editable,
    audit_invoice_snapshot,
    recalculate_totals,
)
from app.vat.vat_messages import (
    VAT_BUSINESS_ACTIVITY_NOT_FOUND,
    VAT_INVOICE_NOT_FOUND_IN_WORK_ITEM,
    VAT_INVOICE_NUMBER_CONFLICT,
    VAT_ITEM_NOT_FOUND,
    VAT_NET_AMOUNT_POSITIVE_REQUIRED,
)
from app.vat.vat_amounts import split_gross_amount


def update_invoice(
    work_item_repo: VatWorkItemRepository,
    invoice_repo: VatInvoiceRepository,
    *,
    item_id: int,
    invoice_id: int,
    performed_by: int,
    patch: dict,
):
    """Update an existing invoice (partial PATCH). Work item must not be FILED.

    `patch` contains only the fields the client actually sent (exclude_unset).
    A key present with value ``None`` clears a clearable nullable field; the
    request schema already rejects null for non-nullable fields.
    """

    # Presence-aware reads: `_sent(key)` => the client included the key.
    def _sent(key: str) -> bool:
        return key in patch

    gross_amount = patch.get("gross_amount")
    invoice_number = patch.get("invoice_number")
    expense_category = patch.get("expense_category")
    rate_type = patch.get("rate_type")
    business_activity_id = patch.get("business_activity_id")

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

    if invoice_number and invoice_number != invoice.invoice_number:
        existing = invoice_repo.get_by_number(item_id, invoice.invoice_type, invoice_number)
        if existing:
            raise ConflictError(
                VAT_INVOICE_NUMBER_CONFLICT.format(invoice_number=invoice_number),
                ErrorCode.VAT_CONFLICT,
            )

    # business_activity_id: explicit null clears the FK; a non-null value is
    # validated against the work item's legal entity.
    if business_activity_id is not None:
        db = getattr(work_item_repo, "db", None)
        record = ClientRecordRepository(db).get_by_id(item.client_record_id) if db else None
        business = BusinessRepository(db).get_by_id(business_activity_id) if db else None
        if not business or not record or business.legal_entity_id != record.legal_entity_id:
            raise AppError(
                VAT_BUSINESS_ACTIVITY_NOT_FOUND,
                code=ErrorCode.BUSINESS_ACTIVITY_NOT_FOUND,
                status_code=404,
            )

    if gross_amount is not None and gross_amount <= 0:
        raise AppError(
            VAT_NET_AMOUNT_POSITIVE_REQUIRED, code=ErrorCode.VAT_NET_NOT_POSITIVE, status_code=400
        )

    # Validate the merged effective counterparty pair: a partial PATCH that
    # clears or changes only one side must not leave the persisted pair
    # inconsistent (e.g. counterparty_id=null while type stays il_business).
    effective_counterparty_id = (
        patch["counterparty_id"] if _sent("counterparty_id") else invoice.counterparty_id
    )
    effective_counterparty_id_type = (
        patch["counterparty_id_type"]
        if _sent("counterparty_id_type")
        else invoice.counterparty_id_type
    )
    validate_counterparty_pair(effective_counterparty_id, effective_counterparty_id_type)

    snapshot_before = audit_invoice_snapshot(invoice)

    # Only fields the client actually sent are applied (true partial PATCH).
    update_fields: dict = {
        key: patch[key]
        for key in (
            "invoice_number",
            "invoice_date",
            "counterparty_name",
            "counterparty_id",
            "counterparty_id_type",
            "expense_category",
            "rate_type",
            "document_type",
            "business_activity_id",
        )
        if _sent(key)
    }

    # Recompute net/vat only when gross_amount or rate_type was sent.
    effective_rate_type = rate_type if _sent("rate_type") else invoice.rate_type
    effective_gross = (
        gross_amount
        if _sent("gross_amount")
        else float(invoice.net_amount) + float(invoice.vat_amount)
    )
    if _sent("gross_amount") or _sent("rate_type"):
        net_amount, vat_amount = split_gross_amount(
            effective_gross,
            effective_rate_type,
            int(item.period[:4]),
        )
        update_fields["net_amount"] = float(net_amount)
        update_fields["vat_amount"] = float(vat_amount)
        effective_net = float(net_amount)
    else:
        effective_net = float(invoice.net_amount)
    # Recompute deduction_rate only when expense_category was sent (schema
    # rejects a null category, so a sent value is always a real category).
    if _sent("expense_category"):
        update_fields["deduction_rate"] = get_vat_deduction_rate_for_category(
            int(item.period[:4]), expense_category.value
        )
    _threshold = Decimal(
        str(get_financial_value(int(item.period[:4]), "exceptional_invoice_threshold_ils").value)
    )
    update_fields["is_exceptional"] = Decimal(str(effective_net)) > _threshold

    updated = invoice_repo.update(invoice_id, **update_fields)

    recalculate_totals(work_item_repo, invoice_repo, item_id)

    work_item_repo.append_audit(
        work_item_id=item_id,
        performed_by=performed_by,
        action=ACTION_INVOICE_UPDATED,
        old_value=snapshot_before,
        new_value=audit_invoice_snapshot(updated),
    )

    return updated
