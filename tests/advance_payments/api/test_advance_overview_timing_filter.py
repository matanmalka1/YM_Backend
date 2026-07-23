"""Tests for advance payment overview server-backed timing_status filter."""

from decimal import Decimal
from itertools import count

from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.common.enums import AdvancePaymentFrequency
from tests.helpers.identity import seed_client_identity

_seq = count(1)
PATH = "/api/v1/advance-payments/overview"


def _client_record(db, *, full_name: str):
    idx = next(_seq)
    return seed_client_identity(
        db,
        full_name=full_name,
        id_number=f"TMG{idx:06d}",
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )


def _seed_overdue_and_on_time(test_db):
    """Same query `year` (period-based), but opposite timing_status.

    - period "2026-01" materializes to due_date 2026-02-16 -> already past -> overdue
      (pending, never paid).
    - period "2026-12" materializes to due_date 2027-01-17 -> still ahead -> on_time.
    """
    overdue_record = _client_record(test_db, full_name="Timing Overdue Client")
    on_time_record = _client_record(test_db, full_name="Timing OnTime Client")

    service = AdvancePaymentService(test_db)
    overdue_payment = service.create_payment_for_client(
        client_record_id=overdue_record.id,
        period="2026-01",
        period_months_count=1,
        expected_amount=Decimal("500"),
    )
    on_time_payment = service.create_payment_for_client(
        client_record_id=on_time_record.id,
        period="2026-12",
        period_months_count=1,
        expected_amount=Decimal("700"),
    )
    test_db.commit()
    return overdue_record, overdue_payment, on_time_record, on_time_payment


def test_timing_status_overdue_returns_only_overdue_row(client, test_db, advisor_headers):
    overdue_record, overdue_payment, on_time_record, on_time_payment = _seed_overdue_and_on_time(
        test_db
    )

    resp = client.get(
        f"{PATH}?year=2026&timing_status=overdue&page=1&page_size=50",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    ids = {item["id"] for item in data["items"]}
    assert overdue_payment.id in ids
    assert on_time_payment.id not in ids
    for item in data["items"]:
        assert item["timing_status"] == "overdue"


def test_timing_status_on_time_returns_only_on_time_row(client, test_db, advisor_headers):
    overdue_record, overdue_payment, on_time_record, on_time_payment = _seed_overdue_and_on_time(
        test_db
    )

    resp = client.get(
        f"{PATH}?year=2026&timing_status=on_time&page=1&page_size=50",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    ids = {item["id"] for item in data["items"]}
    assert on_time_payment.id in ids
    assert overdue_payment.id not in ids
    for item in data["items"]:
        assert item["timing_status"] == "on_time"


def test_timing_status_shrinks_kpi_totals(client, test_db, advisor_headers):
    overdue_record, overdue_payment, on_time_record, on_time_payment = _seed_overdue_and_on_time(
        test_db
    )

    unfiltered = client.get(
        f"{PATH}?year=2026&page=1&page_size=50",
        headers=advisor_headers,
    )
    overdue_only = client.get(
        f"{PATH}?year=2026&timing_status=overdue&page=1&page_size=50",
        headers=advisor_headers,
    )

    assert unfiltered.status_code == 200
    assert overdue_only.status_code == 200
    unfiltered_total_expected = float(unfiltered.json()["total_expected"])
    overdue_total_expected = float(overdue_only.json()["total_expected"])
    assert overdue_total_expected < unfiltered_total_expected
    assert overdue_total_expected >= float(overdue_payment.expected_amount)


def test_timing_status_invalid_value_returns_422(client, test_db, advisor_headers):
    resp = client.get(
        f"{PATH}?year=2026&timing_status=not_a_value&page=1&page_size=10",
        headers=advisor_headers,
    )

    assert resp.status_code == 422
