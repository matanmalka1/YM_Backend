"""#42 envelope guard for VAT list responses.

Binder intakes (PaginatedResponse[BinderIntakeResponse]) and correspondence
(tests/communications/test_correspondence_schemas.py) already have explicit
envelope guards. These tests pin the two VAT list schemas to the standard
PaginatedResponse shape — items/total/page/page_size, nothing else.
"""

from app.vat.schemas.vat_invoice_schema import VatInvoiceListResponse
from app.vat.schemas.vat_report import VatWorkItemListResponse

_STANDARD_ENVELOPE_FIELDS = {"items", "total", "page", "page_size"}


def test_vat_work_item_list_response_uses_standard_envelope():
    assert set(VatWorkItemListResponse.model_fields) == _STANDARD_ENVELOPE_FIELDS
    assert "total_pages" not in VatWorkItemListResponse.model_fields


def test_vat_invoice_list_response_uses_standard_envelope():
    assert set(VatInvoiceListResponse.model_fields) == _STANDARD_ENVELOPE_FIELDS
    assert "total_pages" not in VatInvoiceListResponse.model_fields
