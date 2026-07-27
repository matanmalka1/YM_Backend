"""API tests for POST /advance-payments/bulk-mark-paid."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.common.enums import AdvancePaymentFrequency

URL = "/api/v1/advance-payments/bulk-mark-paid"


def _client_record(client_factory, advance_rate=Decimal("10")):
    return client_factory(
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
        advance_rate=advance_rate,
    )


def _payment(db, client_record, period, *, turnover=Decimal("50000"), paid=None):
    payment = AdvancePaymentService(db).create_payment_for_client(
        client_record_id=client_record.id,
        period=period,
        period_months_count=1,
        turnover_amount=turnover,
        paid_amount=paid,
    )
    db.commit()
    return payment


def _post(client, headers, payload):
    return client.post(URL, json=payload, headers={**headers, "X-Idempotency-Key": str(uuid4())})


def test_bulk_mark_paid_tops_up_pending_and_partial(
    client, test_db, advisor_headers, client_factory
):
    record = _client_record(client_factory)
    pending = _payment(test_db, record, "2026-03")
    partial = _payment(test_db, record, "2026-04", paid=Decimal("1000"))

    resp = _post(
        client,
        advisor_headers,
        {
            "payment_ids": [pending.id, partial.id],
            "paid_at": "2026-04-16T00:00:00",
            "payment_method": "direct_debit",
            "reference_prefix": "BATCH-04",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert sorted(data["updated"]) == sorted([pending.id, partial.id])
    assert data["skipped"] == []

    test_db.expire_all()
    for payment_id in (pending.id, partial.id):
        row = test_db.get(type(pending), payment_id)
        assert row.status == AdvancePaymentStatus.PAID
        assert row.paid_amount == row.expected_amount
        assert row.payment_reference == f"BATCH-04-{payment_id}"
        assert row.paid_at is not None
        assert row.paid_at.date() == date(2026, 4, 16)


def test_bulk_mark_paid_skips_by_reason(client, test_db, advisor_headers, client_factory):
    record = _client_record(client_factory)
    already_paid = _payment(test_db, record, "2026-05")
    already_paid = AdvancePaymentService(test_db).update_payment_for_client(
        record.id, already_paid.id, actor_id=None, paid_amount=already_paid.expected_amount
    )
    test_db.commit()
    no_amount = _payment(test_db, record, "2026-06", turnover=None)

    resp = _post(
        client,
        advisor_headers,
        {"payment_ids": [already_paid.id, no_amount.id, 999999]},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["updated"] == []
    reasons = {item["id"]: item["reason"] for item in data["skipped"]}
    assert reasons == {
        already_paid.id: "already_paid",
        no_amount.id: "no_amount",
        999999: "not_found",
    }


def test_bulk_mark_paid_keeps_existing_method_and_reference_when_omitted(
    client, test_db, advisor_headers, client_factory
):
    record = _client_record(client_factory)
    payment = _payment(test_db, record, "2026-07")

    resp = _post(client, advisor_headers, {"payment_ids": [payment.id]})

    assert resp.status_code == 200
    test_db.expire_all()
    row = test_db.get(type(payment), payment.id)
    assert row.status == AdvancePaymentStatus.PAID
    assert row.payment_method is None
    assert row.payment_reference is None


def test_bulk_mark_paid_rejects_duplicates(client, test_db, advisor_headers, client_factory):
    record = _client_record(client_factory)
    payment = _payment(test_db, record, "2026-08")

    resp = _post(client, advisor_headers, {"payment_ids": [payment.id, payment.id]})

    assert resp.status_code == 422


def test_bulk_mark_paid_forbidden_for_secretary(client, test_db, secretary_headers, client_factory):
    record = _client_record(client_factory)
    payment = _payment(test_db, record, "2026-09")

    resp = _post(client, secretary_headers, {"payment_ids": [payment.id]})

    assert resp.status_code == 403
