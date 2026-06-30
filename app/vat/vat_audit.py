"""Audit helpers for VAT work item / invoice events (generic EntityAuditLog).

Work-item lifecycle events anchor on ``entity_type=vat_work_item``; invoice
events anchor on ``entity_type=vat_invoice`` with the owning work item carried in
``metadata_json.vat_work_item_id``. Writes go through :class:`EntityAuditWriter`
so they are validated fail-closed and appended in the caller's transaction (§17).
"""

from __future__ import annotations

from app.vat.models.vat_invoice import VatInvoice
from app.vat.models.vat_work_item import VatWorkItem


def _tax_year(period: str) -> int:
    return int(period[:4])


def work_item_metadata(item: VatWorkItem) -> dict:
    """metadata_json for vat_work_item rows (§8)."""
    return {
        "client_record_id": item.client_record_id,
        "period": item.period,
        "tax_year": _tax_year(item.period),
    }


def invoice_metadata(item: VatWorkItem, *, invoice_number: str, business_id: int | None) -> dict:
    """metadata_json for vat_invoice rows (§8); owning work item is referenced here."""
    meta: dict = {
        "client_record_id": item.client_record_id,
        "vat_work_item_id": item.id,
        "invoice_number": invoice_number,
        "period": item.period,
        "tax_year": _tax_year(item.period),
    }
    if business_id is not None:
        meta["business_id"] = business_id
    return meta


def invoice_snapshot(invoice: VatInvoice) -> dict:
    """old_value/new_value snapshot for vat_invoice rows."""
    return {
        "invoice_id": invoice.id,
        "type": invoice.invoice_type.value,
        "number": invoice.invoice_number,
        "vat_amount": str(invoice.vat_amount),
    }
