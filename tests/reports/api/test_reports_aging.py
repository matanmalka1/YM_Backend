from datetime import date, timedelta
from decimal import Decimal
from itertools import count

from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from tests.helpers.identity import seed_business, seed_client_identity

_client_seq = count(1)


def _client_and_business(db):
    seq = next(_client_seq)
    client = seed_client_identity(
        db,
        full_name=f"Aging Client {seq}",
        id_number=f"11111111{seq}",
    )
    business = seed_business(
        db,
        legal_entity_id=client.legal_entity_id,
        business_name=client.full_name,
        opened_at=date.today(),
    )
    db.commit()
    db.refresh(business)
    business.client_id = client.id
    return client, business


def _charge(db, client_id: int, business_id: int, amount: Decimal, issued_days_ago: int):
    issued_at = date.today() - timedelta(days=issued_days_ago)
    charge = Charge(
        client_record_id=client_id,
        business_id=business_id,
        amount=amount,
        charge_type=ChargeType.CONSULTATION_FEE,
        status=ChargeStatus.ISSUED,
        issued_at=issued_at,
        created_at=issued_at,
    )
    db.add(charge)
    db.commit()
    db.refresh(charge)
    return charge


def test_aging_report_buckets_and_sorting(client, test_db, advisor_headers):
    client_a, business_a = _client_and_business(test_db)
    client_b, business_b = _client_and_business(test_db)

    # Client A: mix across buckets
    _charge(test_db, client_a.id, business_a.id, Decimal("100"), issued_days_ago=10)  # current
    _charge(test_db, client_a.id, business_a.id, Decimal("200"), issued_days_ago=45)  # 30
    _charge(test_db, client_a.id, business_a.id, Decimal("300"), issued_days_ago=75)  # 60
    _charge(test_db, client_a.id, business_a.id, Decimal("400"), issued_days_ago=120)  # 90+

    # Client B: single 90+ should sort below A because total is smaller
    _charge(test_db, client_b.id, business_b.id, Decimal("150"), issued_days_ago=200)

    resp = client.get("/api/v1/reports/aging", headers=advisor_headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_outstanding"] == "1150.00"
    assert body["summary"]["total_current"] == "100.00"
    assert body["summary"]["total_30_days"] == "200.00"
    assert body["summary"]["total_60_days"] == "300.00"
    assert body["summary"]["total_90_plus"] == "550.00"

    items = body["items"]
    assert len(items) == 2
    # Sorted by total outstanding desc
    assert items[0]["client_record_id"] == client_a.id
    assert items[0]["current"] == "100.00"
    assert items[0]["days_30"] == "200.00"
    assert items[0]["days_60"] == "300.00"
    assert items[0]["days_90_plus"] == "400.00"
    assert items[0]["total_outstanding"] == "1000.00"
    assert items[0]["oldest_invoice_days"] >= 120


def test_aging_report_paginated_large_dataset(client, test_db, advisor_headers):
    for _ in range(55):
        seeded_client, b = _client_and_business(test_db)
        _charge(test_db, seeded_client.id, b.id, Decimal("1"), issued_days_ago=5)

    resp = client.get("/api/v1/reports/aging", headers=advisor_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 55
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert len(body["items"]) == 50
    assert body["summary"]["total_clients"] >= 55
