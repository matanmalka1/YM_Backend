"""Tests for advance payment overview filters."""

from datetime import date
from itertools import count

from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.clients.models.client_record import ClientRecord
from app.common.enums import AdvancePaymentFrequency
from tests.helpers.identity import seed_business, seed_client_identity
from tests.helpers.tax_calendar_links import create_linked_advance_payment

_seq = count(1)
PATH = "/api/v1/advance-payments/overview"


def _business(db):
    idx = next(_seq)
    client = seed_client_identity(
        db,
        full_name=f"Overview Test Client {idx}",
        id_number=f"OVW{idx:06d}",
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    business = seed_business(
        db,
        legal_entity_id=client.legal_entity_id,
        business_name=f"Overview Biz {idx}",
        opened_at=date.today(),
    )
    db.commit()
    db.refresh(business)
    business.client_record_id = client.id
    return business


def test_overview_filter_by_due_date(client, test_db, advisor_headers):
    b = _business(test_db)
    repo = AdvancePaymentRepository(test_db)
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=b.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
    )
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=b.client_record_id,
        period="2026-02",
        period_months_count=1,
        due_date=date(2026, 3, 15),
    )

    resp = client.get(
        f"{PATH}?year=2026&due_date=2026-02-15&page=1&page_size=10",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["due_date"] == "2026-02-15"


def test_overview_due_date_includes_monthly_and_bimonthly_rows(
    client,
    test_db,
    advisor_headers,
):
    monthly_business = _business(test_db)
    bimonthly_business = _business(test_db)
    repo = AdvancePaymentRepository(test_db)
    shared_due_date = date(2026, 3, 15)
    monthly = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=monthly_business.client_record_id,
        period="2026-02",
        period_months_count=1,
        due_date=shared_due_date,
    )
    bimonthly = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=bimonthly_business.client_record_id,
        period="2026-01",
        period_months_count=2,
        due_date=shared_due_date,
    )

    resp = client.get(
        f"{PATH}?year=2026&due_date=2026-03-15&page=1&page_size=10",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert {item["id"] for item in data["items"]} == {monthly.id, bimonthly.id}
    assert {item["period_months_count"] for item in data["items"]} == {1, 2}


def test_overview_filter_by_period_months_count(client, test_db, advisor_headers):
    b = _business(test_db)
    repo = AdvancePaymentRepository(test_db)
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=b.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
    )
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=b.client_record_id,
        period="2026-03",
        period_months_count=2,
        due_date=date(2026, 4, 15),
    )

    resp = client.get(
        f"{PATH}?year=2026&period_months_count=2&page=1&page_size=10",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["period_months_count"] == 2


def test_overview_client_search_by_official_name(client, test_db, advisor_headers):
    b = _business(test_db)
    repo = AdvancePaymentRepository(test_db)
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=b.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
    )
    name_part = b.legal_entity.official_name[:8]

    resp = client.get(
        f"{PATH}?year=2026&client_search={name_part}&page=1&page_size=10",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


def test_overview_client_search_by_id_number(client, test_db, advisor_headers):
    b = _business(test_db)
    repo = AdvancePaymentRepository(test_db)
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=b.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
    )
    id_number = b.legal_entity.id_number

    resp = client.get(
        f"{PATH}?year=2026&client_search={id_number}&page=1&page_size=10",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_overview_client_search_by_office_client_number(client, test_db, advisor_headers):
    b = _business(test_db)
    cr = test_db.get(ClientRecord, b.client_record_id)
    cr.office_client_number = 88771
    test_db.commit()

    repo = AdvancePaymentRepository(test_db)
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=b.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
    )

    resp = client.get(
        f"{PATH}?year=2026&client_search=88771&page=1&page_size=10",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_overview_filter_by_exact_client_record_id(client, test_db, advisor_headers):
    target = _business(test_db)
    same_name = _business(test_db)
    same_name.legal_entity.official_name = target.legal_entity.official_name
    test_db.commit()

    repo = AdvancePaymentRepository(test_db)
    target_payment = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=target.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
    )
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=same_name.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
    )

    resp = client.get(
        f"{PATH}?year=2026&client_record_id={target.client_record_id}&page=1&page_size=10",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == target_payment.id
