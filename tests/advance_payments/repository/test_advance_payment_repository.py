from datetime import date
from decimal import Decimal
from itertools import count

from sqlalchemy import text

from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.advance_payments.repositories.advance_payment_aggregation_repository import (
    AdvancePaymentAggregationRepository,
)
from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.businesses.models.business import Business
from app.common.enums import VatType
from app.tax_calendar.services.tax_calendar_materialization_service import (
    TaxCalendarMaterializationService,
)
from app.users.models.user import UserRole
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem
from app.vat.repositories.vat_client_summary_repository import (
    VatClientSummaryRepository,
)
from tests.factories import create_user
from tests.helpers.identity import seed_client_identity
from tests.helpers.tax_calendar_links import create_linked_advance_payment

_seq = count(1)


def _create_user(test_db):
    user = create_user(
        test_db,
        full_name="Creator",
        email=f"creator{next(_seq)}@example.com",
        password="pass",
        role=UserRole.ADVISOR,
        is_active=True,
        commit=True,
    )
    return user


def _create_business(test_db, name: str, id_number: str):
    client = seed_client_identity(test_db, full_name=name, id_number=id_number)
    business = Business(
        legal_entity_id=client.legal_entity_id,
        business_name=f"{name} Business",
        opened_at=date(2024, 1, 1),
    )
    test_db.add(business)
    test_db.commit()
    test_db.refresh(business)
    business.client_record_id = client.id
    return business


def test_list_by_client_record_year_filters_and_orders(test_db):
    repo = AdvancePaymentRepository(test_db)
    business = _create_business(test_db, "Client One", "100000001")

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
    repo.update_payment(february, status=AdvancePaymentStatus.PAID)

    items, total = repo.list_by_client_record_year(
        client_record_id=business.client_record_id, year=2025, status=None
    )
    assert total == 2
    assert [p.period for p in items] == ["2025-01", "2025-02"]

    pending_items, pending_total = repo.list_by_client_record_year(
        client_record_id=business.client_record_id,
        year=2025,
        status=[AdvancePaymentStatus.PENDING],
    )
    assert pending_total == 1
    assert pending_items[0].id == january.id


def test_get_annual_output_vat_returns_sum_or_none(test_db):
    repo = VatClientSummaryRepository(test_db)
    business = _create_business(test_db, "VAT Client", "100000002")
    user = _create_user(test_db)
    materializer = TaxCalendarMaterializationService(test_db)
    jan_entry = materializer.ensure_periodic_entry("vat", "2025-01", 1)
    feb_entry = materializer.ensure_periodic_entry("vat", "2025-02", 1)
    prev_entry = materializer.ensure_periodic_entry("vat", "2024-12", 1)

    january = VatWorkItem(
        client_record_id=business.client_record_id,
        created_by=user.id,
        period="2025-01",
        period_type=VatType.MONTHLY,
        status=VatWorkItemStatus.FILED,
        total_output_vat=Decimal("150.50"),
        total_input_vat=Decimal("0"),
        net_vat=Decimal("150.50"),
        tax_calendar_entry_id=jan_entry.id,
        due_date_original=jan_entry.due_date,
        due_date_effective=jan_entry.due_date,
    )
    february = VatWorkItem(
        client_record_id=business.client_record_id,
        created_by=user.id,
        period="2025-02",
        period_type=VatType.MONTHLY,
        status=VatWorkItemStatus.FILED,
        total_output_vat=Decimal("149.50"),
        total_input_vat=Decimal("0"),
        net_vat=Decimal("149.50"),
        tax_calendar_entry_id=feb_entry.id,
        due_date_original=feb_entry.due_date,
        due_date_effective=feb_entry.due_date,
    )
    previous_year = VatWorkItem(
        client_record_id=business.client_record_id,
        created_by=user.id,
        period="2024-12",
        period_type=VatType.MONTHLY,
        status=VatWorkItemStatus.FILED,
        total_output_vat=Decimal("999.00"),
        total_input_vat=Decimal("0"),
        net_vat=Decimal("999.00"),
        tax_calendar_entry_id=prev_entry.id,
        due_date_original=prev_entry.due_date,
        due_date_effective=prev_entry.due_date,
    )
    test_db.add_all([january, february, previous_year])
    test_db.commit()

    assert repo.get_annual_output_vat(
        client_record_id=business.client_record_id, year=2025
    ) == Decimal("300.00")


def test_list_overview_payments_filters_by_month_and_status(test_db):
    repo = AdvancePaymentRepository(test_db)
    aggregation_repo = AdvancePaymentAggregationRepository(test_db)
    business_a = _create_business(test_db, "Alpha", "100000003")
    business_b = _create_business(test_db, "Beta", "100000004")

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
    repo.update_payment(payment_b, status=AdvancePaymentStatus.PAID)

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
        statuses=[AdvancePaymentStatus.PENDING, AdvancePaymentStatus.PAID],
    )

    assert len(rows) == 2
    ids = {r.id for r in rows}
    assert payment_a.id in ids
    assert payment_b.id in ids


def test_list_by_client_record_year_handles_partial_status(test_db):
    """PARTIAL status round-trips through ORM correctly."""
    repo = AdvancePaymentRepository(test_db)
    business = _create_business(test_db, "Legacy Client", "100000005")

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
        text("UPDATE advance_payments SET status = 'partial' WHERE id = :payment_id"),
        {"payment_id": payment.id},
    )
    test_db.commit()

    items, total = repo.list_by_client_record_year(
        client_record_id=business.client_record_id, year=2026, status=None
    )
    assert total == 1
    assert items[0].status == AdvancePaymentStatus.PARTIAL
