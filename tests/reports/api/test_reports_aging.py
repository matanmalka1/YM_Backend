from datetime import date, timedelta
from decimal import Decimal

from app.charges.models.charge import ChargeStatus, ChargeType


def _charge(
    charge_factory, client_id: int, business_id: int, amount: Decimal, issued_days_ago: int
):
    issued_at = date.today() - timedelta(days=issued_days_ago)
    return charge_factory(
        client_record_id=client_id,
        business_id=business_id,
        amount=amount,
        charge_type=ChargeType.CONSULTATION_FEE,
        status=ChargeStatus.ISSUED,
        issued_at=issued_at,
        commit=True,
    )


def test_aging_report_buckets_and_sorting(
    client, test_db, advisor_headers, create_client_with_business, charge_factory
):
    client_a, business_a = create_client_with_business()
    client_b, business_b = create_client_with_business()

    # Client A: mix across buckets
    _charge(
        charge_factory, client_a.id, business_a.id, Decimal("100"), issued_days_ago=10
    )  # current
    _charge(charge_factory, client_a.id, business_a.id, Decimal("200"), issued_days_ago=45)  # 30
    _charge(charge_factory, client_a.id, business_a.id, Decimal("300"), issued_days_ago=75)  # 60
    _charge(charge_factory, client_a.id, business_a.id, Decimal("400"), issued_days_ago=120)  # 90+

    # Client B: single 90+ should sort below A because total is smaller
    _charge(charge_factory, client_b.id, business_b.id, Decimal("150"), issued_days_ago=200)

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


def test_aging_report_paginated_large_dataset(
    client, test_db, advisor_headers, create_client_with_business, charge_factory
):
    for _ in range(55):
        seeded_client, b = create_client_with_business()
        _charge(charge_factory, seeded_client.id, b.id, Decimal("1"), issued_days_ago=5)

    resp = client.get("/api/v1/reports/aging", headers=advisor_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 55
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert len(body["items"]) == 50
    assert body["summary"]["total_clients"] >= 55
