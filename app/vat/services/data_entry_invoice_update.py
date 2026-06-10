"""Invoice update flow for VAT work items."""

from datetime import datetime
from decimal import Decimal

from app.businesses.repositories.business_repository import BusinessRepository
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.vat.integrations.tax_rules_financials import (
    get_financial_value,
    get_vat_deduction_rate_for_category,
)
from app.vat.models.vat_enums import (
    CounterpartyIdType,
    DocumentType,
    ExpenseCategory,
    VatRateType,
)
from app.vat.repositories.vat_invoice_repository import VatInvoiceRepository
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.services.constants import ACTION_INVOICE_UPDATED
from app.vat.services.data_entry_common import (
    assert_editable,
    audit_invoice_snapshot,
    recalculate_totals,
)
from app.vat.services.messages import (
    VAT_BUSINESS_ACTIVITY_NOT_FOUND,
    VAT_INVOICE_NOT_FOUND_IN_WORK_ITEM,
    VAT_INVOICE_NUMBER_CONFLICT,
    VAT_ITEM_NOT_FOUND,
    VAT_NET_AMOUNT_POSITIVE_REQUIRED,
)
from app.vat.services.vat_amounts import split_gross_amount


def update_invoice(
    work_item_repo: VatWorkItemRepository,
    invoice_repo: VatInvoiceRepository,
    *,
    item_id: int,
    invoice_id: int,
    performed_by: int,
    gross_amount: float | None = None,
    invoice_number: str | None = None,
    invoice_date: datetime | None = None,
    counterparty_name: str | None = None,
    counterparty_id: str | None = None,
    counterparty_id_type: CounterpartyIdType | None = None,
    expense_category: ExpenseCategory | None = None,
    rate_type: VatRateType | None = None,
    document_type: DocumentType | None = None,
    business_activity_id: int | None = None,
):
    """Update an existing invoice. Work item must not be FILED."""
    item = work_item_repo.get_by_id(item_id)
    if not item:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), "VAT.NOT_FOUND")

    assert_editable(item)

    invoice = invoice_repo.get_by_id(invoice_id)
    if not invoice or invoice.work_item_id != item_id:
        raise NotFoundError(
            VAT_INVOICE_NOT_FOUND_IN_WORK_ITEM.format(invoice_id=invoice_id, item_id=item_id),
            "VAT.NOT_FOUND",
        )

    if invoice_number and invoice_number != invoice.invoice_number:
        existing = invoice_repo.get_by_number(item_id, invoice.invoice_type, invoice_number)
        if existing:
            raise ConflictError(
                VAT_INVOICE_NUMBER_CONFLICT.format(invoice_number=invoice_number),
                "VAT.CONFLICT",
            )

    if business_activity_id is not None:
        db = getattr(work_item_repo, "db", None)
        record = ClientRecordRepository(db).get_by_id(item.client_record_id) if db else None
        business = BusinessRepository(db).get_by_id(business_activity_id) if db else None
        if not business or not record or business.legal_entity_id != record.legal_entity_id:
            raise AppError(
                VAT_BUSINESS_ACTIVITY_NOT_FOUND,
                code="BUSINESS_ACTIVITY.NOT_FOUND",
                status_code=404,
            )

    if gross_amount is not None and gross_amount <= 0:
        raise AppError(
            VAT_NET_AMOUNT_POSITIVE_REQUIRED, code="VAT.NET_NOT_POSITIVE", status_code=400
        )

    snapshot_before = audit_invoice_snapshot(invoice)

    update_fields: dict = {
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "counterparty_name": counterparty_name,
        "counterparty_id": counterparty_id,
        "counterparty_id_type": counterparty_id_type,
        "expense_category": expense_category,
        "rate_type": rate_type,
        "document_type": document_type,
        "business_activity_id": business_activity_id,
    }
    effective_rate_type = rate_type if rate_type is not None else invoice.rate_type
    effective_gross = (
        gross_amount
        if gross_amount is not None
        else float(invoice.net_amount) + float(invoice.vat_amount)
    )
    if gross_amount is not None or rate_type is not None:
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
    if expense_category is not None:
        update_fields["deduction_rate"] = get_vat_deduction_rate_for_category(
            int(item.period[:4]), expense_category.value
        )
    _threshold = Decimal(
        str(get_financial_value(int(item.period[:4]), "exceptional_invoice_threshold_ils").value)
    )
    update_fields["is_exceptional"] = Decimal(str(effective_net)) > _threshold

    updated = invoice_repo.update(
        invoice_id,
        **{k: v for k, v in update_fields.items() if v is not None or k == "is_exceptional"},
    )

    recalculate_totals(work_item_repo, invoice_repo, item_id)

    work_item_repo.append_audit(
        work_item_id=item_id,
        performed_by=performed_by,
        action=ACTION_INVOICE_UPDATED,
        old_value=snapshot_before,
        new_value=audit_invoice_snapshot(updated),
    )

    return updated
