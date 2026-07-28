"""Invoice add flow for VAT work items."""

from datetime import datetime
from uuid import uuid4

from app.audit.audit_constants import (
    ACTION_VAT_INVOICE_CREATED,
    ENTITY_VAT_INVOICE,
    ENTITY_VAT_WORK_ITEM,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.businesses.repositories.business_repository import BusinessRepository
from app.clients.client_enums import ClientStatus
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.common.enums import ObligationStatus
from app.common.period_utils import parse_period_year
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.legal_entities.repositories.legal_entity_repository import LegalEntityRepository
from app.vat.models.vat_enums import (
    CounterpartyIdType,
    DocumentType,
    ExpenseCategory,
    InvoiceType,
    VatRateType,
)
from app.vat.repositories.vat_invoice_repository import VatInvoiceRepository
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.vat_amounts import split_gross_amount
from app.vat.vat_audit import invoice_metadata, invoice_snapshot, work_item_metadata
from app.vat.vat_constants import CATEGORY_LABELS_SERVER
from app.vat.vat_data_entry_common import (
    assert_editable,
    check_osek_patur_ceiling,
    recalculate_totals,
    resolve_invoice_derived_fields,
)
from app.vat.vat_messages import (
    VAT_ADD_INVOICE_INVALID_STATUS,
    VAT_AUTO_STATUS_CHANGE_ON_FIRST_INVOICE,
    VAT_BUSINESS_ACTIVITY_WRONG_CLIENT,
    VAT_CLIENT_CLOSED_ADD_INVOICES,
    VAT_INCOME_COUNTERPARTY_NAME,
    VAT_INVOICE_NUMBER_CONFLICT,
    VAT_ITEM_NOT_FOUND,
    VAT_NET_AMOUNT_POSITIVE_REQUIRED,
    VAT_UNKNOWN_COUNTERPARTY_NAME,
)


def add_invoice(
    work_item_repo: VatWorkItemRepository,
    invoice_repo: VatInvoiceRepository,
    *,
    item_id: int,
    created_by: int,
    invoice_type: InvoiceType,
    invoice_number: str | None,
    invoice_date: datetime | None,
    counterparty_name: str | None,
    gross_amount: float,
    counterparty_id: str | None = None,
    counterparty_id_type: CounterpartyIdType | None = None,
    expense_category: ExpenseCategory | None = None,
    rate_type: VatRateType = VatRateType.STANDARD,
    document_type: DocumentType | None = None,
    business_activity_id: int | None = None,
    actor_display_name: str | None = None,
):
    """Add an invoice to a work item. Validation delegated to resolve_invoice_derived_fields."""
    item = work_item_repo.get_by_id(item_id)
    if not item:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), ErrorCode.VAT_NOT_FOUND)

    assert_editable(item)

    db = getattr(work_item_repo, "db", None)
    record = ClientRecordRepository(db).get_by_id(item.client_record_id) if db else None
    if not record:
        raise NotFoundError(
            VAT_ITEM_NOT_FOUND.format(item_id=item_id),
            ErrorCode.VAT_CLIENT_RECORD_NOT_FOUND,
        )
    legal_entity = (
        LegalEntityRepository(db).get_by_id(record.legal_entity_id) if db and record else None
    )

    if record.status == ClientStatus.CLOSED:
        raise AppError(VAT_CLIENT_CLOSED_ADD_INVOICES, ErrorCode.VAT_CLIENT_CLOSED)

    if business_activity_id is not None:
        business = BusinessRepository(db).get_by_id(business_activity_id) if db else None
        if not business or not record or business.legal_entity_id != record.legal_entity_id:
            raise AppError(
                VAT_BUSINESS_ACTIVITY_WRONG_CLIENT,
                ErrorCode.BUSINESS_ACTIVITY_WRONG_CLIENT,
            )

    if gross_amount <= 0:
        raise AppError(VAT_NET_AMOUNT_POSITIVE_REQUIRED, ErrorCode.VAT_NET_NOT_POSITIVE)

    net_amount, vat_amount = split_gross_amount(
        gross_amount, rate_type, parse_period_year(item.period)
    )

    derived = resolve_invoice_derived_fields(
        invoice_type,
        expense_category,
        document_type,
        counterparty_id,
        float(net_amount),
        float(vat_amount),
        year=parse_period_year(item.period),
    )
    deduction_rate = derived["deduction_rate"]
    is_exceptional = derived["is_exceptional"]

    ceiling_warning = False
    if invoice_type == InvoiceType.INCOME and legal_entity:
        scope_id = item.client_record_id
        ceiling_warning = check_osek_patur_ceiling(
            legal_entity, invoice_repo, scope_id, item.period, float(net_amount)
        )

    # Auto-fill optional fields when not provided by caller
    if not invoice_number:
        invoice_number = f"{item.period}-{invoice_type.value}-{uuid4().hex[:8]}"
    if not invoice_date:
        invoice_date = datetime.strptime(f"{item.period}-01", "%Y-%m-%d")
    if not counterparty_name:
        if invoice_type == InvoiceType.INCOME:
            counterparty_name = VAT_INCOME_COUNTERPARTY_NAME
        else:
            counterparty_name = CATEGORY_LABELS_SERVER.get(
                expense_category.value if expense_category else "",
                VAT_UNKNOWN_COUNTERPARTY_NAME,
            )

    existing = invoice_repo.get_by_number(item_id, invoice_type, invoice_number)
    if existing:
        raise ConflictError(
            VAT_INVOICE_NUMBER_CONFLICT.format(invoice_number=invoice_number),
            ErrorCode.VAT_CONFLICT,
        )

    writer = EntityAuditWriter(work_item_repo.db)

    original_status = item.status

    if original_status == ObligationStatus.INPUT_RECEIVED:
        work_item_repo.update_status(item_id, ObligationStatus.IN_PROGRESS)
        writer.record_status_change(
            ENTITY_VAT_WORK_ITEM,
            item_id,
            created_by,
            ObligationStatus.INPUT_RECEIVED.value,
            ObligationStatus.IN_PROGRESS.value,
            note=VAT_AUTO_STATUS_CHANGE_ON_FIRST_INVOICE,
            actor_display_name=actor_display_name,
            metadata_json=work_item_metadata(item),
        )
    elif original_status not in (
        ObligationStatus.IN_PROGRESS,
        ObligationStatus.AWAITING_VERIFICATION,
    ):
        raise AppError(
            VAT_ADD_INVOICE_INVALID_STATUS.format(status=original_status.value),
            ErrorCode.VAT_INVALID_STATUS,
        )

    invoice = invoice_repo.create(
        work_item_id=item_id,
        created_by=created_by,
        invoice_type=invoice_type,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        counterparty_name=counterparty_name,
        counterparty_id=counterparty_id,
        counterparty_id_type=counterparty_id_type,
        net_amount=float(net_amount),
        vat_amount=float(vat_amount),
        expense_category=expense_category,
        rate_type=rate_type,
        deduction_rate=float(deduction_rate),
        document_type=document_type,
        is_exceptional=is_exceptional,
        business_activity_id=business_activity_id,
    )

    recalculate_totals(work_item_repo, invoice_repo, item_id)

    writer.record_action(
        ENTITY_VAT_INVOICE,
        invoice.id,
        created_by,
        ACTION_VAT_INVOICE_CREATED,
        new_value=invoice_snapshot(invoice),
        actor_display_name=actor_display_name,
        metadata_json=invoice_metadata(
            item, invoice_number=invoice.invoice_number, business_id=invoice.business_activity_id
        ),
    )

    return invoice, ceiling_warning
