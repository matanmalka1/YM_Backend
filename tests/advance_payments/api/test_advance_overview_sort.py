"""Tests for advance payment overview server-backed sorting."""

from datetime import date
from decimal import Decimal
from itertools import count

from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.common.enums import AdvancePaymentFrequency
from tests.helpers.identity import seed_business, seed_client_identity
from tests.helpers.tax_calendar_links import create_linked_advance_payment

_seq = count(1)
PATH = "/api/v1/advance-payments/overview"


def _business(db, *, full_name: str):
    idx = next(_seq)
    client = seed_client_identity(
        db,
        full_name=full_name,
        id_number=f"SRT{idx:06d}",
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    business = seed_business(
        db,
        legal_entity_id=client.legal_entity_id,
        business_name=f"Sort Biz {idx}",
        opened_at=date.today(),
    )
    db.commit()
    db.refresh(business)
    business.client_record_id = client.id
    return business


def test_overview_sort_by_expected_amount_desc(client, test_db, advisor_headers):
    low = _business(test_db, full_name="Sort Client Low")
    high = _business(test_db, full_name="Sort Client High")
    repo = AdvancePaymentRepository(test_db)
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=low.client_record_id,
        period="2026-04",
        period_months_count=1,
        due_date=date(2026, 5, 15),
        expected_amount=Decimal("100"),
    )
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=high.client_record_id,
        period="2026-04",
        period_months_count=1,
        due_date=date(2026, 5, 15),
        expected_amount=Decimal("900"),
    )

    resp = client.get(
        f"{PATH}?year=2026&month=4&sort_by=expected_amount&order=desc&page=1&page_size=10",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    amounts = [
        item["expected_amount"]
        for item in data["items"]
        if item["client_record_id"] in {low.client_record_id, high.client_record_id}
    ]
    assert amounts == sorted(amounts, key=float, reverse=True)
    assert float(amounts[0]) == 900.0


def test_overview_sort_by_client_name_asc(client, test_db, advisor_headers):
    b_client = _business(test_db, full_name="Sort AAA Client")
    a_client = _business(test_db, full_name="Sort ZZZ Client")
    repo = AdvancePaymentRepository(test_db)
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=b_client.client_record_id,
        period="2026-05",
        period_months_count=1,
        due_date=date(2026, 6, 15),
    )
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=a_client.client_record_id,
        period="2026-05",
        period_months_count=1,
        due_date=date(2026, 6, 15),
    )

    resp = client.get(
        f"{PATH}?year=2026&month=5&sort_by=client_name&order=asc&page=1&page_size=10",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    names = [item["client_name"] for item in data["items"]]
    assert names == sorted(names)


def test_overview_invalid_sort_by_returns_422(client, test_db, advisor_headers):
    resp = client.get(
        f"{PATH}?year=2026&sort_by=not_a_field&page=1&page_size=10",
        headers=advisor_headers,
    )

    assert resp.status_code == 422
