from decimal import Decimal
from types import SimpleNamespace

import pytest
from tax_rules import get_financial

from app.common.enums import EntityType
from app.core.exceptions import AppError
from app.vat.models.vat_enums import InvoiceType, VatWorkItemStatus
from app.vat.vat_constants import OSEK_PATUR_CEILING_WARNING_RATE
from app.vat.services.vat_data_entry_common import (
    assert_transition_allowed,
    check_osek_patur_ceiling,
    resolve_invoice_derived_fields,
)

OSEK_PATUR_CEILING_ILS = Decimal(str(get_financial(2026, "osek_patur_ceiling_ils").value))


def test_data_entry_common_rejects_invalid_transition_and_derives_invoice_fields():
    item = SimpleNamespace(status=VatWorkItemStatus.PENDING_MATERIALS)
    with pytest.raises(AppError):
        assert_transition_allowed(item, VatWorkItemStatus.FILED)

    derived = resolve_invoice_derived_fields(
        invoice_type=InvoiceType.INCOME,
        expense_category=None,
        document_type=None,
        counterparty_id=None,
        net_amount=100,
        vat_amount=17,
    )
    assert "deduction_rate" in derived


def test_osek_patur_ceiling_uses_2026_threshold_and_boundary_behavior():
    osek_business = SimpleNamespace(entity_type=EntityType.OSEK_PATUR)

    class _InvoiceRepo:
        def __init__(self, total):
            self.total = total

        def sum_income_net_by_client_year(self, client_id, year):
            assert year == 2026
            return self.total

    assert OSEK_PATUR_CEILING_ILS == 122833
    assert check_osek_patur_ceiling(osek_business, _InvoiceRepo(122832), 1, "2026-01", 1) is True

    with pytest.raises(AppError) as exc:
        check_osek_patur_ceiling(osek_business, _InvoiceRepo(122833), 1, "2026-01", 0.01)
    assert exc.value.code == "VAT.OSEK_PATUR_CEILING_EXCEEDED"
    assert "122833.00" in str(exc.value.message)


def test_osek_patur_ceiling_warning_threshold_is_80_percent():
    osek_business = SimpleNamespace(entity_type=EntityType.OSEK_PATUR)
    warning_threshold = OSEK_PATUR_CEILING_ILS * OSEK_PATUR_CEILING_WARNING_RATE

    class _InvoiceRepo:
        def __init__(self, total):
            self.total = total

        def sum_income_net_by_client_year(self, client_id, year):
            return self.total

    assert (
        check_osek_patur_ceiling(
            osek_business,
            _InvoiceRepo(warning_threshold - 1),
            1,
            "2026-01",
            0.5,
        )
        is False
    )
    assert (
        check_osek_patur_ceiling(
            osek_business,
            _InvoiceRepo(warning_threshold - 1),
            1,
            "2026-01",
            1,
        )
        is True
    )
