from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.clients.models.client_record import ClientRecord
from app.utils.time_utils import utcnow
from tests.tax_calendar.api.grouped_helpers import (
    add_advance_payment,
    add_annual_report,
    add_vat_item,
    advance_entry,
    annual_entry,
    headers,
    vat_entry,
)


def _path(entry_id: int) -> str:
    return f"/api/v1/tax-calendar/groups/{entry_id}/items"


def _items(response):
    return response.json()["items"]


def test_unauthenticated_request_is_rejected(client, test_db):
    entry = vat_entry(test_db)
    test_db.commit()

    response = client.get(_path(entry.id))

    assert response.status_code == 401


def test_advisor_can_fetch_items(client, auth_token, test_db, test_user):
    entry = vat_entry(test_db)
    add_vat_item(test_db, entry, test_user.id)
    test_db.commit()

    response = client.get(_path(entry.id), headers=headers(auth_token))

    assert response.status_code == 200
    assert response.json()["tax_calendar_entry_id"] == entry.id


def test_secretary_can_fetch_items(client, secretary_token, test_db, test_user):
    entry = vat_entry(test_db)
    add_vat_item(test_db, entry, test_user.id)
    test_db.commit()

    response = client.get(_path(entry.id), headers=headers(secretary_token))

    assert response.status_code == 200
    assert len(_items(response)) == 1


def test_group_items_are_paginated(client, auth_token, test_db, test_user):
    entry = vat_entry(test_db)
    first = add_vat_item(test_db, entry, test_user.id)
    add_vat_item(test_db, entry, test_user.id)
    test_db.commit()

    response = client.get(
        f"{_path(entry.id)}?page=1&page_size=1",
        headers=headers(auth_token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert payload["total"] == 2
    assert [item["source_id"] for item in payload["items"]] == [first.id]


def test_vat_linked_item_appears_with_client_and_effective_due_date(
    client, auth_token, test_db, test_user
):
    entry = vat_entry(test_db)
    item = add_vat_item(test_db, entry, test_user.id)
    test_db.commit()

    response = client.get(_path(entry.id), headers=headers(auth_token))

    assert response.status_code == 200
    data = _items(response)[0]
    assert data["source_type"] == "vat_work_item"
    assert data["source_id"] == item.id
    assert data["client_record_id"] == item.client_record_id
    assert data["client_name"].startswith("Calendar VAT")
    assert data["effective_due_date"] == "2026-02-20"


def test_advance_payment_linked_item_appears(client, auth_token, test_db):
    entry = advance_entry(test_db)
    payment = add_advance_payment(test_db, entry, status=AdvancePaymentStatus.PAID)
    test_db.commit()

    response = client.get(_path(entry.id), headers=headers(auth_token))

    assert response.status_code == 200
    data = _items(response)[0]
    assert data["source_type"] == "advance_payment"
    assert data["source_id"] == payment.id
    assert data["done"] is True


def test_annual_report_linked_item_appears(client, auth_token, test_db):
    entry = annual_entry(test_db)
    report = add_annual_report(test_db, entry)
    test_db.commit()

    response = client.get(_path(entry.id), headers=headers(auth_token))

    assert response.status_code == 200
    data = _items(response)[0]
    assert data["source_type"] == "annual_report"
    assert data["source_id"] == report.id
    assert data["effective_due_date"] == "2027-07-31"


def test_unlinked_business_objects_are_not_returned(client, auth_token, test_db, test_user):
    entry = vat_entry(test_db)
    other_entry = vat_entry(test_db, 2027)
    add_vat_item(test_db, other_entry, test_user.id)
    test_db.commit()

    response = client.get(_path(entry.id), headers=headers(auth_token))

    assert response.status_code == 200
    assert _items(response) == []


def test_deleted_rows_are_not_returned(client, auth_token, test_db, test_user):
    entry = vat_entry(test_db)
    item = add_vat_item(test_db, entry, test_user.id)
    item.deleted_at = utcnow()
    test_db.commit()

    response = client.get(_path(entry.id), headers=headers(auth_token))

    assert response.status_code == 200
    assert _items(response) == []


def test_soft_deleted_client_rows_are_not_returned_vat(client, auth_token, test_db, test_user):
    entry = vat_entry(test_db)
    item = add_vat_item(test_db, entry, test_user.id)
    test_db.get(ClientRecord, item.client_record_id).deleted_at = utcnow()
    test_db.commit()

    response = client.get(_path(entry.id), headers=headers(auth_token))

    assert response.status_code == 200
    assert _items(response) == []


def test_soft_deleted_client_rows_are_not_returned_advance(client, auth_token, test_db):
    entry = advance_entry(test_db)
    payment = add_advance_payment(test_db, entry)
    test_db.get(ClientRecord, payment.client_record_id).deleted_at = utcnow()
    test_db.commit()

    response = client.get(_path(entry.id), headers=headers(auth_token))

    assert response.status_code == 200
    assert _items(response) == []


def test_soft_deleted_client_rows_are_not_returned_annual(client, auth_token, test_db):
    entry = annual_entry(test_db)
    report = add_annual_report(test_db, entry)
    test_db.get(ClientRecord, report.client_record_id).deleted_at = utcnow()
    test_db.commit()

    response = client.get(_path(entry.id), headers=headers(auth_token))

    assert response.status_code == 200
    assert _items(response) == []


def test_missing_calendar_entry_returns_404(client, auth_token):
    response = client.get(_path(999999), headers=headers(auth_token))

    assert response.status_code == 404
