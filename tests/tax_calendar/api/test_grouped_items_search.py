"""Tests for /groups/{id}/items client_search and client_record_id filter."""

from sqlalchemy import select

from app.clients.models.client_record import ClientRecord
from app.legal_entities.models.legal_entity import LegalEntity
from tests.tax_calendar.api.grouped_helpers import (
    add_vat_item,
    headers,
    vat_entry,
)


def _path(entry_id: int) -> str:
    return f"/api/v1/tax-calendar/groups/{entry_id}/items"


def test_items_client_search_by_name(client, auth_token, test_db, test_user):
    entry = vat_entry(test_db)
    add_vat_item(test_db, entry, test_user.id)
    test_db.commit()

    resp = client.get(
        f"{_path(entry.id)}?client_search=Calendar+VAT",
        headers=headers(auth_token),
    )

    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


def test_items_client_search_by_id_number(client, auth_token, test_db, test_user):
    entry = vat_entry(test_db)
    item = add_vat_item(test_db, entry, test_user.id)
    test_db.commit()

    id_number = test_db.scalar(
        select(LegalEntity.id_number)
        .join(ClientRecord, ClientRecord.legal_entity_id == LegalEntity.id)
        .where(ClientRecord.id == item.client_record_id)
    )

    resp = client.get(
        f"{_path(entry.id)}?client_search={id_number}",
        headers=headers(auth_token),
    )

    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["id_number"] == id_number


def test_items_client_search_by_office_number(client, auth_token, test_db, test_user):
    entry = vat_entry(test_db)
    item = add_vat_item(test_db, entry, test_user.id)
    cr = test_db.get(ClientRecord, item.client_record_id)
    cr.office_client_number = 9901
    test_db.commit()

    resp = client.get(
        f"{_path(entry.id)}?client_search=9901",
        headers=headers(auth_token),
    )

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_items_client_search_no_match_returns_empty(client, auth_token, test_db, test_user):
    entry = vat_entry(test_db)
    add_vat_item(test_db, entry, test_user.id)
    test_db.commit()

    resp = client.get(
        f"{_path(entry.id)}?client_search=ZZZNOTEXIST",
        headers=headers(auth_token),
    )

    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_items_client_record_id_filter(client, auth_token, test_db, test_user):
    entry = vat_entry(test_db)
    first = add_vat_item(test_db, entry, test_user.id)
    add_vat_item(test_db, entry, test_user.id)
    test_db.commit()

    resp = client.get(
        f"{_path(entry.id)}?client_record_id={first.client_record_id}",
        headers=headers(auth_token),
    )

    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["source_id"] == first.id


def test_items_response_includes_id_number_field(client, auth_token, test_db, test_user):
    entry = vat_entry(test_db)
    add_vat_item(test_db, entry, test_user.id)
    test_db.commit()

    resp = client.get(_path(entry.id), headers=headers(auth_token))

    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert "id_number" in item
