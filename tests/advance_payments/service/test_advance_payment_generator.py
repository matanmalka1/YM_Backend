from datetime import date
from itertools import count

import pytest
from sqlalchemy import select

from app.advance_payments.models.advance_payment import AdvancePayment
from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.businesses.models.business import Business
from app.clients.client_enums import ClientStatus
from app.common.enums import AdvancePaymentFrequency, VatType
from app.core.exceptions import ConflictError, NotFoundError
from tests.helpers.tax_calendar_links import create_linked_advance_payment


def generate_annual_schedule(
    client_record_id, year, db, period_months_count=None, reference_date=None
):
    return AdvancePaymentService(db).generate_annual_schedule(
        client_record_id,
        year,
        period_months_count=period_months_count,
        reference_date=reference_date,
    )


_seq = count(1)


def _business(create_client_with_business) -> Business:
    idx = next(_seq)
    _client, business = create_client_with_business(
        full_name=f"Advance Gen Client {idx}",
        id_number=f"555666{idx:03d}",
        business_name=f"Advance Gen Business {idx}",
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    return business


def _closed_client_record_id(client_factory) -> int:
    idx = next(_seq)
    client = client_factory(
        full_name=f"Advance Gen Closed Client {idx}",
        id_number=f"555777{idx:03d}",
        status=ClientStatus.CLOSED,
    )
    return client.id


def test_generate_annual_schedule_creates_all_12_months(test_db, create_client_with_business):
    business = _business(create_client_with_business)

    created, skipped = generate_annual_schedule(
        business.client_record_id, 2026, test_db, reference_date=date(2025, 12, 31)
    )

    assert skipped == 0
    assert len(created) == 12
    assert {p.period for p in created} == {f"2026-{m:02d}" for m in range(1, 13)}
    assert all(p.due_date is not None for p in created)
    assert all(p.tax_calendar_entry_id is not None for p in created)


def test_generate_annual_schedule_is_idempotent_for_existing_periods(
    test_db, create_client_with_business
):
    business = _business(create_client_with_business)
    repo = AdvancePaymentRepository(test_db)

    existing = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
        expected_amount=100,
    )

    created, skipped = generate_annual_schedule(
        business.client_record_id, 2026, test_db, reference_date=date(2025, 12, 31)
    )

    assert skipped == 1
    assert len(created) == 11
    assert all(p.period != existing.period for p in created)

    rows = test_db.scalars(
        select(AdvancePayment).filter(
            AdvancePayment.client_record_id == business.client_record_id,
            AdvancePayment.period.like("2026-%"),
        )
    ).all()
    assert len(rows) == 12


def test_generate_annual_schedule_missing_business_raises_not_found(test_db):
    with pytest.raises(NotFoundError) as exc:
        generate_annual_schedule(999999, 2026, test_db)

    assert exc.value.code == "ADVANCE_PAYMENT.CLIENT_RECORD_NOT_FOUND"


def test_generate_annual_schedule_ineligible_client_raises_shared_guard_code(
    test_db, client_factory
):
    """Schedule generation blocks on the same shared guard as single create.

    Previously 403 CLIENT.CLOSED from this domain's own check; now 409
    CLIENT_RECORD.CLOSED, because the block is a fact about the client record's
    state rather than the caller's permissions.
    """
    client_record_id = _closed_client_record_id(client_factory)

    with pytest.raises(ConflictError) as exc:
        generate_annual_schedule(client_record_id, 2026, test_db)

    assert exc.value.code == "CLIENT_RECORD.CLOSED"


def test_generate_annual_schedule_bimonthly_due_dates_rollover_year(
    test_db, create_client_with_business
):
    business = _business(create_client_with_business)
    business.legal_entity.advance_payment_frequency = AdvancePaymentFrequency.BIMONTHLY
    test_db.commit()

    created, skipped = generate_annual_schedule(
        business.client_record_id,
        2026,
        test_db,
        period_months_count=2,
        reference_date=date(2025, 12, 31),
    )

    assert skipped == 0
    assert len(created) == 6
    periods = [p.period for p in created]
    assert periods == ["2026-01", "2026-03", "2026-05", "2026-07", "2026-09", "2026-11"]
    nov = next(p for p in created if p.period == "2026-11")
    assert nov.due_date == date(2027, 1, 17)


def test_generate_annual_schedule_skips_periods_before_reference_date(
    test_db, create_client_with_business
):
    business = _business(create_client_with_business)

    created, skipped = generate_annual_schedule(
        business.client_record_id,
        2026,
        test_db,
        period_months_count=1,
        reference_date=date(2026, 4, 1),
    )

    assert skipped == 2  # Jan (due Feb 15), Feb (due Mar 15)
    assert len(created) == 10
    assert all(p.due_date >= date(2026, 4, 1) for p in created)


def test_generate_annual_schedule_uses_advance_payment_frequency_independent_of_vat(
    test_db,
    create_client_with_business,
):
    business = _business(create_client_with_business)
    # VAT bimonthly but advance monthly — should produce 12, not 6
    business.legal_entity.vat_reporting_frequency = VatType.BIMONTHLY
    business.legal_entity.advance_payment_frequency = AdvancePaymentFrequency.MONTHLY
    test_db.commit()

    created, skipped = generate_annual_schedule(
        business.client_record_id, 2026, test_db, reference_date=date(2025, 12, 31)
    )

    assert skipped == 0
    assert len(created) == 12
    assert all(p.period_months_count == 1 for p in created)
