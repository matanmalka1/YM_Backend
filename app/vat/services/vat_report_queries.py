from datetime import UTC, datetime

from app.common.enums import SubmissionMethod, VatType
from app.core.exceptions import NotFoundError
from app.vat.models.vat_enums import InvoiceType, VatWorkItemStatus
from app.vat.repositories.vat_invoice_repository import VatInvoiceRepository
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.schemas.vat_report import VatWorkItemStatusSummaryResponse
from app.vat.services.messages import VAT_ITEM_NOT_FOUND


def deadline_fields_from_snapshot(item, submission_method: SubmissionMethod | None = None) -> dict:
    """Compute deadline fields from stored due_date_effective (preferred path for linked items).

    due_date_effective already incorporates any calendar-level extension (e.g. exception
    overrides in tax_rules_config). Do NOT add online-extension days here — that would
    double-count an extension already baked into the snapshot.
    """
    statutory_deadline = item.due_date_original or item.due_date_effective
    effective_deadline = item.due_date_effective or statutory_deadline
    submission_deadline = effective_deadline
    extended_deadline = effective_deadline
    today = datetime.now(UTC).date()
    days = (submission_deadline - today).days
    return {
        "submission_deadline": submission_deadline,
        "statutory_deadline": statutory_deadline,
        "extended_deadline": extended_deadline,
        "days_until_deadline": days,
        "is_overdue": days < 0,
    }


def get_vat_deadline_fields(item, submission_method: SubmissionMethod | None = None) -> dict:
    """Return deadline fields from the stored TaxCalendarEntry snapshot."""
    if getattr(item, "due_date_effective", None) is None:
        raise ValueError(f"VatWorkItem {getattr(item, 'id', None)} is missing due_date_effective")
    return deadline_fields_from_snapshot(item, submission_method)


def get_work_item(work_item_repo: VatWorkItemRepository, item_id: int):
    item = work_item_repo.get_by_id(item_id)
    if not item:
        raise NotFoundError(VAT_ITEM_NOT_FOUND.format(item_id=item_id), "VAT.NOT_FOUND")
    return item


def list_client_work_items_paginated(
    work_item_repo: VatWorkItemRepository,
    client_record_id: int,
    page: int = 1,
    page_size: int = 200,
):
    items = work_item_repo.list_by_client_record_paginated(
        client_record_id,
        page=page,
        page_size=page_size,
    )
    total = work_item_repo.count_by_client_record(client_record_id)
    return items, total


def normalize_lookup_period(period: str) -> str:
    return period[:7] if len(period) > 7 else period


def get_work_item_by_client_period(
    work_item_repo: VatWorkItemRepository,
    client_record_id: int,
    period: str,
):
    return work_item_repo.get_by_client_record_period(
        client_record_id,
        normalize_lookup_period(period),
    )


def list_work_items_by_status(
    work_item_repo: VatWorkItemRepository,
    status: VatWorkItemStatus,
    page: int = 1,
    page_size: int = 50,
    period: str | None = None,
    client_name: str | None = None,
    period_type: VatType | None = None,
):
    items = work_item_repo.list_by_status(
        status,
        page=page,
        page_size=page_size,
        period=period,
        period_type=period_type,
        client_name=client_name,
    )
    total = work_item_repo.count_by_status(
        status,
        period=period,
        period_type=period_type,
        client_name=client_name,
    )
    return items, total


def list_all_work_items(
    work_item_repo: VatWorkItemRepository,
    page: int = 1,
    page_size: int = 50,
    period: str | None = None,
    client_name: str | None = None,
    period_type: VatType | None = None,
):
    items = work_item_repo.list_all(
        page=page,
        page_size=page_size,
        period=period,
        period_type=period_type,
        client_name=client_name,
    )
    total = work_item_repo.count_all(
        period=period,
        period_type=period_type,
        client_name=client_name,
    )
    return items, total


def get_status_summary(
    work_item_repo: VatWorkItemRepository,
    *,
    year: int | None = None,
    period_type: VatType | None = None,
    client_name: str | None = None,
) -> VatWorkItemStatusSummaryResponse:
    counts = work_item_repo.count_by_status_summary(
        year=year,
        period_type=period_type,
        client_name=client_name,
    )
    return VatWorkItemStatusSummaryResponse(
        **{status.value: counts.get(status, 0) for status in VatWorkItemStatus}
    )


def list_invoices(
    invoice_repo: VatInvoiceRepository,
    item_id: int,
    invoice_type: InvoiceType | None = None,
):
    return invoice_repo.list_by_work_item(item_id, invoice_type=invoice_type)


def get_audit_trail(work_item_repo: VatWorkItemRepository, item_id: int, limit: int, offset: int):
    return work_item_repo.get_audit_trail(item_id, limit, offset)


def count_audit_trail(work_item_repo: VatWorkItemRepository, item_id: int):
    return work_item_repo.count_audit_trail(item_id)
