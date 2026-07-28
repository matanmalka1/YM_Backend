from decimal import Decimal

import pytest

from app.advance_payments.advance_payment_calculator import (
    calculate_expected_amount,
    derive_annual_income_from_vat,
)
from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.common.enums import AdvancePaymentFrequency, ObligationStatus, VatType
from app.core.exceptions import AppError, ConflictError


def test_create_payment_duplicate_period_raises_conflict(test_db, create_client_with_business):
    _client, business = create_client_with_business(
        vat_reporting_frequency=VatType.MONTHLY,
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    service = AdvancePaymentService(test_db)

    service.create_payment_for_client(
        client_record_id=business.client_record_id,
        period="2026-01",
        period_months_count=1,
    )

    with pytest.raises(ConflictError):
        service.create_payment_for_client(
            client_record_id=business.client_record_id,
            period="2026-01",
            period_months_count=1,
        )


def test_calculate_expected_amount_rounds_half_up():
    amount = calculate_expected_amount(Decimal("1000"), Decimal("10"))
    assert amount == Decimal("8")


def test_derive_income_zero_rate_raises():
    with pytest.raises(AppError) as exc_info:
        derive_annual_income_from_vat(Decimal("1000"), vat_rate=Decimal("0"))
    assert exc_info.value.code == "ADVANCE_PAYMENT.RATE_INVALID"


def test_list_payments_filters_by_status(test_db, create_client_with_business):
    _client, business = create_client_with_business(
        vat_reporting_frequency=VatType.MONTHLY,
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    service = AdvancePaymentService(test_db)

    first = service.create_payment_for_client(
        client_record_id=business.client_record_id,
        period="2026-01",
        period_months_count=1,
        expected_amount=Decimal("100"),
    )
    second = service.create_payment_for_client(
        client_record_id=business.client_record_id,
        period="2026-02",
        period_months_count=1,
        expected_amount=Decimal("200"),
    )
    service.update_payment_for_client(
        business.client_record_id,
        second.id,
        status=ObligationStatus.AWAITING_VERIFICATION,
        paid_amount=Decimal("200"),
    )

    all_items, total = service.list_payments_for_client(business.client_record_id, year=2026)
    assert total == 2
    assert [p.id for p in all_items] == [first.id, second.id]

    paid_items, paid_total = service.list_payments_for_client(
        business.client_record_id,
        year=2026,
        status=[ObligationStatus.AWAITING_VERIFICATION],
    )
    assert paid_total == 1
    assert paid_items[0].id == second.id
