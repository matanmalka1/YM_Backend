from datetime import date
from decimal import Decimal
from itertools import count

from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from tests.helpers.identity import seed_business, seed_client_identity
from tests.helpers.tax_calendar_links import create_linked_advance_payment

_client_seq = count(1)


def _business(db):
    from app.common.enums import AdvancePaymentFrequency

    id_number = f"66666666{next(_client_seq)}"
    client = seed_client_identity(
        db,
        full_name="Advance Client",
        id_number=id_number,
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    business = seed_business(
        db,
        legal_entity_id=client.legal_entity_id,
        business_name="Advance Overview Business",
        opened_at=date.today(),
    )
    db.commit()
    db.refresh(business)
    business.client_record_id = client.id
    return business


def test_create_advance_payment_and_conflict(client, test_db, advisor_headers):
    business = _business(test_db)

    payload = {
        "period": "2026-03",
        "period_months_count": 1,
        "turnover_amount": "40000.00",
        "advance_rate": "3.0",
    }
    first = client.post(
        f"/api/v1/clients/{business.client_record_id}/advance-payments",
        headers=advisor_headers,
        json=payload,
    )
    assert first.status_code == 201
    first_data = first.json()
    assert first_data["period"] == "2026-03"
    assert Decimal(first_data["turnover_amount"]) == Decimal("40000.00")
    assert Decimal(first_data["advance_rate"]) == Decimal("3.00")
    assert Decimal(first_data["calculated_amount"]) == Decimal("1200.00")
    assert Decimal(first_data["expected_amount"]) == Decimal("1200.00")

    conflict = client.post(
        f"/api/v1/clients/{business.client_record_id}/advance-payments",
        headers=advisor_headers,
        json=payload,
    )
    data = conflict.json()
    assert conflict.status_code == 409
    assert data["error"]["code"] == "ADVANCE_PAYMENT.CONFLICT"
    assert isinstance(data["error"]["message"], str)


def test_create_advance_payment_uses_advance_payment_frequency(client, test_db, advisor_headers):
    from app.common.enums import AdvancePaymentFrequency

    business = _business(test_db)
    business.legal_entity.advance_payment_frequency = AdvancePaymentFrequency.BIMONTHLY
    test_db.commit()

    resp = client.post(
        f"/api/v1/clients/{business.client_record_id}/advance-payments",
        headers=advisor_headers,
        json={
            "period": "2026-03",
            "turnover_amount": "40000.00",
            "advance_rate": "3.0",
        },
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["period"] == "2026-03"
    assert data["period_months_count"] == 2


def test_overview_filters_by_status_and_month(client, test_db, advisor_headers):
    business = _business(test_db)
    repo = AdvancePaymentRepository(test_db)
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
    )
    feb = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-02",
        period_months_count=1,
        due_date=date(2026, 3, 15),
    )
    repo.update_payment(feb, status=AdvancePaymentStatus.PAID, paid_amount=Decimal("1200"))

    resp = client.get(
        "/api/v1/advance-payments/overview?year=2026&month=2&status=paid&page=1&page_size=10",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["period"] == "2026-02"
    assert item["status"] == "paid"


def test_overview_filters_by_due_date_and_client_search(client, test_db, advisor_headers):
    first_business = _business(test_db)
    second_business = _business(test_db)
    repo = AdvancePaymentRepository(test_db)
    first = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=first_business.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
    )
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=second_business.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
    )
    first_id_number = first_business.legal_entity.id_number

    resp = client.get(
        "/api/v1/advance-payments/overview"
        f"?year=2026&due_date=2026-02-15&client_search={first_id_number}"
        "&page=1&page_size=1",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert data["total"] == 1
    assert data["items"][0]["id"] == first.id


def test_overview_batches_returns_numeric_counts(client, test_db, advisor_headers):
    business = _business(test_db)
    repo = AdvancePaymentRepository(test_db)
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-03",
        period_months_count=1,
        due_date=date(2020, 4, 15),
    )

    resp = client.get(
        "/api/v1/advance-payments/overview/batches?year=2026",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    row = next(item for item in resp.json() if item["month"] == 3)
    for key in (
        "client_count",
        "missing_turnover_count",
        "overdue_count",
        "pending_count",
    ):
        assert isinstance(row[key], int)
        assert row[key] >= 0


def test_overview_batches_filter_by_exact_client_record_id(client, test_db, advisor_headers):
    target = _business(test_db)
    other = _business(test_db)
    repo = AdvancePaymentRepository(test_db)
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=target.client_record_id,
        period="2026-03",
        period_months_count=1,
        due_date=date(2026, 4, 15),
    )
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=other.client_record_id,
        period="2026-03",
        period_months_count=1,
        due_date=date(2026, 4, 15),
    )

    resp = client.get(
        f"/api/v1/advance-payments/overview/batches?year=2026&client_record_id={target.client_record_id}",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    row = next(item for item in resp.json() if item["month"] == 3)
    assert row["client_count"] == 1
