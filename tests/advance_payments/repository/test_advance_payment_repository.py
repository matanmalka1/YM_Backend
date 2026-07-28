from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.advance_payments.repositories.advance_payment_aggregation_repository import (
    AdvancePaymentAggregationRepository,
)
from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.common.enums import ObligationStatus, VatType
from app.tax_calendar.services.tax_calendar_materialization_service import (
    TaxCalendarMaterializationService,
)
from app.vat.repositories.vat_client_summary_repository import (
    VatClientSummaryRepository,
)
from tests.helpers.tax_calendar_links import create_linked_advance_payment


def test_list_by_client_record_year_filters_and_orders(test_db, create_client_with_business):
    repo = AdvancePaymentRepository(test_db)
    _client, business = create_client_with_business(
        full_name="Client One", id_number="100000001", opened_at=date(2024, 1, 1)
    )

    january = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2025-01",
        period_months_count=1,
        due_date=date(2025, 2, 15),
        expected_amount=Decimal("100.00"),
    )
    february = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2025-02",
        period_months_count=1,
        due_date=date(2025, 3, 15),
        expected_amount=Decimal("200.00"),
    )
    repo.update_payment(february, status=ObligationStatus.SUBMITTED)

    items, total = repo.list_by_client_record_year(
        client_record_id=business.client_record_id, year=2025, status=None
    )
    assert total == 2
    assert [p.period for p in items] == ["2025-01", "2025-02"]

    pending_items, pending_total = repo.list_by_client_record_year(
        client_record_id=business.client_record_id,
        year=2025,
        status=[ObligationStatus.AWAITING_INPUT],
    )
    assert pending_total == 1
    assert pending_items[0].id == january.id


def test_get_annual_output_vat_returns_sum_or_none(
    test_db, create_client_with_business, user_factory, vat_work_item_factory
):
    repo = VatClientSummaryRepository(test_db)
    _client, business = create_client_with_business(
        full_name="VAT Client", id_number="100000002", opened_at=date(2024, 1, 1)
    )
    user = user_factory(full_name="Creator", password="pass")
    materializer = TaxCalendarMaterializationService(test_db)
    jan_entry = materializer.ensure_periodic_entry("vat", "2025-01", 1)
    feb_entry = materializer.ensure_periodic_entry("vat", "2025-02", 1)
    prev_entry = materializer.ensure_periodic_entry("vat", "2024-12", 1)

    vat_work_item_factory(
        client_record_id=business.client_record_id,
        created_by=user.id,
        period="2025-01",
        period_type=VatType.MONTHLY,
        status=ObligationStatus.SUBMITTED,
        total_output_vat=Decimal("150.50"),
        total_input_vat=Decimal("0"),
        net_vat=Decimal("150.50"),
        tax_calendar_entry_id=jan_entry.id,
        due_date_original=jan_entry.due_date,
        due_date_effective=jan_entry.due_date,
    )
    vat_work_item_factory(
        client_record_id=business.client_record_id,
        created_by=user.id,
        period="2025-02",
        period_type=VatType.MONTHLY,
        status=ObligationStatus.SUBMITTED,
        total_output_vat=Decimal("149.50"),
        total_input_vat=Decimal("0"),
        net_vat=Decimal("149.50"),
        tax_calendar_entry_id=feb_entry.id,
        due_date_original=feb_entry.due_date,
        due_date_effective=feb_entry.due_date,
    )
    vat_work_item_factory(
        client_record_id=business.client_record_id,
        created_by=user.id,
        period="2024-12",
        period_type=VatType.MONTHLY,
        status=ObligationStatus.SUBMITTED,
        total_output_vat=Decimal("999.00"),
        total_input_vat=Decimal("0"),
        net_vat=Decimal("999.00"),
        tax_calendar_entry_id=prev_entry.id,
        due_date_original=prev_entry.due_date,
        due_date_effective=prev_entry.due_date,
    )
    test_db.commit()

    assert repo.get_annual_output_vat(
        client_record_id=business.client_record_id, year=2025
    ) == Decimal("300.00")


def test_list_overview_payments_filters_by_month_and_status(test_db, create_client_with_business):
    repo = AdvancePaymentRepository(test_db)
    aggregation_repo = AdvancePaymentAggregationRepository(test_db)
    _client_a, business_a = create_client_with_business(
        full_name="Alpha", id_number="100000003", opened_at=date(2024, 1, 1)
    )
    _client_b, business_b = create_client_with_business(
        full_name="Beta", id_number="100000004", opened_at=date(2024, 1, 1)
    )

    payment_a = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business_a.client_record_id,
        period="2025-01",
        period_months_count=1,
        due_date=date(2025, 2, 10),
    )
    payment_b = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business_b.client_record_id,
        period="2025-01",
        period_months_count=1,
        due_date=date(2025, 2, 12),
    )
    repo.update_payment(payment_b, status=ObligationStatus.SUBMITTED)

    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business_a.client_record_id,
        period="2025-02",
        period_months_count=1,
        due_date=date(2025, 3, 10),
    )

    rows = aggregation_repo.list_overview_payments(
        year=2025,
        month=1,
        statuses=[ObligationStatus.AWAITING_INPUT, ObligationStatus.SUBMITTED],
    )

    assert len(rows) == 2
    ids = {r.id for r in rows}
    assert payment_a.id in ids
    assert payment_b.id in ids


def test_list_by_client_record_year_handles_partial_status(test_db, create_client_with_business):
    """PARTIAL status round-trips through ORM correctly."""
    repo = AdvancePaymentRepository(test_db)
    _client, business = create_client_with_business(
        full_name="Legacy Client", id_number="100000005", opened_at=date(2024, 1, 1)
    )

    payment = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-03",
        period_months_count=1,
        due_date=date(2026, 4, 15),
        expected_amount=Decimal("300.00"),
        paid_amount=Decimal("100.00"),
    )

    test_db.execute(
        text("UPDATE advance_payments SET status = 'in_progress' WHERE id = :payment_id"),
        {"payment_id": payment.id},
    )
    test_db.commit()

    items, total = repo.list_by_client_record_year(
        client_record_id=business.client_record_id, year=2026, status=None
    )
    assert total == 1
    assert items[0].status == ObligationStatus.IN_PROGRESS
