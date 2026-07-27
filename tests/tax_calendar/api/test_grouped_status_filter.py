"""Tests for /groups?status= filter and done status correctness."""

from datetime import date

from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.common.enums import AdvancePaymentFrequency
from tests.helpers.tax_calendar_links import (
    PATH,
    advance_entry,
    headers,
)


def _make_past_entry(db):
    return advance_entry(db, year=2020)


def _add_payment(
    advance_payment_factory,
    entry,
    client_record,
    status,
    due_date=date(2020, 2, 15),
):
    return advance_payment_factory(
        client=client_record,
        period="2020-01",
        period_months_count=1,
        due_date=entry.due_date,
        due_date_effective=due_date,
        status=status,
        tax_calendar_entry_id=entry.id,
    )


def _advance_client(client_factory):
    return client_factory(advance_payment_frequency=AdvancePaymentFrequency.MONTHLY)


def test_status_open_returns_only_groups_with_open_items(
    client, auth_token, test_db, client_factory, advance_payment_factory
):
    entry = _make_past_entry(test_db)
    c = _advance_client(client_factory)
    _add_payment(advance_payment_factory, entry, c, AdvancePaymentStatus.PENDING)
    test_db.commit()

    resp = client.get(f"{PATH}?status=open", headers=headers(auth_token))

    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["open_count"] > 0


def test_status_open_excludes_fully_done_groups(
    client, auth_token, test_db, client_factory, advance_payment_factory
):
    entry = _make_past_entry(test_db)
    c = _advance_client(client_factory)
    _add_payment(advance_payment_factory, entry, c, AdvancePaymentStatus.PAID)
    test_db.commit()

    resp = client.get(f"{PATH}?status=open", headers=headers(auth_token))

    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_status_overdue_returns_groups_with_overdue_items(
    client, auth_token, test_db, client_factory, advance_payment_factory
):
    entry = _make_past_entry(test_db)
    c = _advance_client(client_factory)
    _add_payment(advance_payment_factory, entry, c, AdvancePaymentStatus.PENDING)
    test_db.commit()

    resp = client.get(f"{PATH}?status=overdue", headers=headers(auth_token))

    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["overdue_count"] > 0


def test_status_done_requires_all_items_closed(
    client, auth_token, test_db, client_factory, advance_payment_factory
):
    """Group with 1 paid + 1 pending must NOT appear as done."""
    entry = _make_past_entry(test_db)
    c1 = _advance_client(client_factory)
    c2 = _advance_client(client_factory)
    _add_payment(advance_payment_factory, entry, c1, AdvancePaymentStatus.PAID)
    _add_payment(advance_payment_factory, entry, c2, AdvancePaymentStatus.PENDING)
    test_db.commit()

    resp = client.get(f"{PATH}?status=done", headers=headers(auth_token))

    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_status_done_returns_group_when_all_paid(
    client, auth_token, test_db, client_factory, advance_payment_factory
):
    entry = _make_past_entry(test_db)
    c1 = _advance_client(client_factory)
    c2 = _advance_client(client_factory)
    _add_payment(advance_payment_factory, entry, c1, AdvancePaymentStatus.PAID)
    _add_payment(advance_payment_factory, entry, c2, AdvancePaymentStatus.PAID)
    test_db.commit()

    resp = client.get(f"{PATH}?status=done", headers=headers(auth_token))

    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    data = resp.json()["items"][0]
    assert data["open_count"] == 0
    assert data["overdue_count"] == 0
    assert data["linked_count"] == 2


def test_status_done_excludes_empty_groups(client, auth_token, test_db):
    advance_entry(test_db)
    test_db.commit()

    resp = client.get(f"{PATH}?status=done&include_empty=true", headers=headers(auth_token))

    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_groups_paginated_response_shape(client, auth_token, test_db):
    advance_entry(test_db)
    test_db.commit()

    resp = client.get(f"{PATH}?include_empty=true&page=1&page_size=10", headers=headers(auth_token))

    assert resp.status_code == 200
    payload = resp.json()
    assert "items" in payload
    assert "page" in payload
    assert "page_size" in payload
    assert "total" in payload
    assert isinstance(payload["items"], list)
