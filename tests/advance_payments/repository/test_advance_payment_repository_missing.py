from datetime import date
from decimal import Decimal

from app.advance_payments.repositories.advance_payment_aggregation_repository import (
    AdvancePaymentAggregationRepository as AdvancePaymentAnalyticsRepository,
)
from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.common.enums import ObligationStatus
from tests.helpers.tax_calendar_links import create_linked_advance_payment


def test_advance_payment_get_by_id_for_client_and_soft_delete(
    test_db, user_factory, create_client_with_business
):
    repo = AdvancePaymentRepository(test_db)
    _client, business = create_client_with_business(
        full_name="Advance Repo Missing Client",
        business_name="Advance Repo Missing Business",
        opened_at=date(2024, 1, 1),
    )
    actor = user_factory(commit=False)

    payment = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
        expected_amount=Decimal("100.00"),
    )

    fetched = repo.get_by_id_for_client_record(payment.id, business.client_record_id)
    assert fetched is not None
    assert fetched.id == payment.id

    assert repo.soft_delete(payment.id, deleted_by=actor.id) is True
    assert repo.get_by_id(payment.id) is None


def test_advance_payment_exists_for_period_and_sum_paid(test_db, create_client_with_business):
    repo = AdvancePaymentRepository(test_db)
    _client, business = create_client_with_business(
        full_name="Advance Repo Missing Client",
        business_name="Advance Repo Missing Business",
        opened_at=date(2024, 1, 1),
    )

    jan = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
        expected_amount=Decimal("100.00"),
    )
    repo.update_payment(jan, paid_amount=Decimal("100.00"), status=ObligationStatus.SUBMITTED)

    feb = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-02",
        period_months_count=1,
        due_date=date(2026, 3, 15),
        expected_amount=Decimal("200.00"),
    )
    repo.update_payment(feb, paid_amount=Decimal("150.00"), status=ObligationStatus.IN_PROGRESS)

    assert repo.exists_for_period(business.client_record_id, "2026-01") is True
    assert repo.exists_for_period(business.client_record_id, "2026-03") is False
    assert (
        AdvancePaymentAnalyticsRepository(test_db).sum_paid_by_client_year(
            business.client_record_id, 2026
        )
        == 100.0
    )


def test_advance_payment_analytics_annual_kpis(test_db, create_client_with_business):
    repo = AdvancePaymentRepository(test_db)
    analytics = AdvancePaymentAnalyticsRepository(test_db)
    _client, business = create_client_with_business(
        full_name="Advance Repo Missing Client",
        business_name="Advance Repo Missing Business",
        opened_at=date(2024, 1, 1),
    )

    jan = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
        expected_amount=Decimal("100.00"),
    )
    repo.update_payment(jan, paid_amount=Decimal("100.00"), status=ObligationStatus.SUBMITTED)

    feb = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-02",
        period_months_count=1,
        due_date=date(2020, 3, 15),  # past due date → timing_status=overdue
        expected_amount=Decimal("200.00"),
    )
    repo.update_payment(feb, paid_amount=Decimal("0.00"), status=ObligationStatus.AWAITING_INPUT)

    kpis = analytics.get_annual_kpis_for_client(business.client_record_id, 2026)
    assert kpis["total_expected"] == 300.0
    assert kpis["total_paid"] == 100.0
    assert kpis["overdue_count"] == 1
    assert kpis["on_time_count"] == 1
