from datetime import date
from decimal import Decimal
from itertools import count

from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.advance_payments.repositories.advance_payment_turnover_lookup_repository import (
    TurnoverLookupRepository,
)
from app.advance_payments.services.advance_payment_analytics_service import (
    AdvancePaymentAnalyticsService as AdvancePaymentService,
)
from app.businesses.models.business import Business
from app.common.enums import VatType
from app.tax_calendar.services.tax_calendar_materialization_service import (
    TaxCalendarMaterializationService,
)
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem
from tests.helpers.identity import seed_business, seed_client_identity
from tests.helpers.tax_calendar_links import create_linked_advance_payment

_seq = count(1)


def _business(db, idx: int) -> Business:
    uniq = next(_seq)
    client = seed_client_identity(
        db,
        full_name=f"AP Overview Client {idx}",
        id_number=f"321654{uniq:03d}",
    )
    business = seed_business(
        db,
        legal_entity_id=client.legal_entity_id,
        business_name=f"AP Overview Biz {idx}",
        opened_at=date.today(),
    )
    db.commit()
    db.refresh(business)
    business.client_record_id = client.id
    business.client = client
    return business


def _filed_vat_item(db, client_record_id: int, period: str, total_output_net: str):
    entry = TaxCalendarMaterializationService(db).ensure_periodic_entry("vat", period, 1)
    amount = Decimal(total_output_net)
    item = VatWorkItem(
        client_record_id=client_record_id,
        period=period,
        period_type=VatType.MONTHLY,
        status=VatWorkItemStatus.FILED,
        total_output_vat=amount,
        total_output_net=amount,
        total_input_vat=Decimal("0"),
        net_vat=amount,
        created_by=1,
        tax_calendar_entry_id=entry.id,
        due_date_original=entry.due_date,
        due_date_effective=entry.due_date,
    )
    db.add(item)
    db.commit()
    return item


def test_list_overview_returns_rows_sorted_and_total(test_db):
    b1 = _business(test_db, 1)
    b2 = _business(test_db, 2)
    repo = AdvancePaymentRepository(test_db)
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=b2.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
        expected_amount=Decimal("100"),
    )
    paid = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=b1.client_record_id,
        period="2026-02",
        period_months_count=1,
        due_date=date(2026, 3, 15),
        expected_amount=Decimal("200"),
    )
    repo.update_payment(paid, status=AdvancePaymentStatus.PAID, paid_amount=Decimal("200"))

    service = AdvancePaymentService(test_db)
    rows, total = service.list_overview(
        year=2026,
        month=None,
        statuses=[AdvancePaymentStatus.PENDING, AdvancePaymentStatus.PAID],
        page=1,
        page_size=10,
    )

    assert total == 2
    assert rows[0].client_name == b1.client.full_name
    assert rows[1].client_name == b2.client.full_name


def test_get_overview_kpis_collection_rate_rounds(test_db):
    business = _business(test_db, 3)
    repo = AdvancePaymentRepository(test_db)
    partial = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
        expected_amount=Decimal("100"),
    )
    repo.update_payment(partial, paid_amount=Decimal("50"), status=AdvancePaymentStatus.PARTIAL)

    paid = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-02",
        period_months_count=1,
        due_date=date(2026, 3, 15),
        expected_amount=Decimal("200"),
    )
    repo.update_payment(paid, paid_amount=Decimal("200"), status=AdvancePaymentStatus.PAID)

    service = AdvancePaymentService(test_db)
    kpis = service.get_overview_kpis(
        year=2026, statuses=[AdvancePaymentStatus.PARTIAL, AdvancePaymentStatus.PAID]
    )

    assert kpis["total_expected"] == 300.0
    assert kpis["total_paid"] == 250.0
    assert kpis["collection_rate"] == Decimal("83.33")


def test_turnover_lookup_batches_multiple_clients_with_group_by(test_db):
    first = _business(test_db, 4)
    second = _business(test_db, 5)
    first_jan = _filed_vat_item(test_db, first.client_record_id, "2026-01", "100")
    _filed_vat_item(test_db, first.client_record_id, "2026-02", "200")
    second_jan = _filed_vat_item(test_db, second.client_record_id, "2026-01", "300")

    result = TurnoverLookupRepository(test_db).get_turnover_for_many_clients(
        {
            first.client_record_id: [("2026-01", 2)],
            second.client_record_id: [("2026-01", 1)],
        }
    )

    assert result[(first.client_record_id, "2026-01")] == (Decimal("300"), first_jan.id)
    assert result[(second.client_record_id, "2026-01")] == (
        Decimal("300"),
        second_jan.id,
    )


def test_turnover_lookup_expands_periods_across_year_boundary(test_db):
    business = _business(test_db, 6)
    dec = _filed_vat_item(test_db, business.client_record_id, "2026-12", "100")
    _filed_vat_item(test_db, business.client_record_id, "2027-01", "200")

    result = TurnoverLookupRepository(test_db).get_turnover_for_many_clients(
        {business.client_record_id: [("2026-12", 2)]}
    )

    assert result[(business.client_record_id, "2026-12")] == (Decimal("300"), dec.id)
