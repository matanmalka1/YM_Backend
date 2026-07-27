from app.clients.models.client_record import ClientRecord
from app.utils.time_utils import utcnow
from tests.tax_calendar.api.grouped_helpers import (
    PATH,
    add_advance_payment,
    add_annual_report,
    add_vat_item,
    advance_entry,
    annual_entry,
    headers,
    vat_entry,
)


def test_empty_calendar_include_empty_false_returns_empty(client, auth_token, test_db):
    vat_entry(test_db)
    test_db.commit()

    response = client.get(PATH, headers=headers(auth_token))

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


def test_include_empty_true_returns_calendar_rows(client, auth_token, test_db):
    entry = advance_entry(test_db)
    test_db.commit()

    response = client.get(f"{PATH}?include_empty=true", headers=headers(auth_token))

    assert response.status_code == 200
    assert response.json()["items"][0] == {
        "tax_calendar_entry_id": entry.id,
        "obligation_type": "advance_payment",
        "period": "2026-01",
        "period_months_count": 1,
        "tax_year": 2026,
        "regulatory_due_date": "2026-02-15",
        "effective_due_date_min": "2026-02-15",
        "effective_due_date_max": "2026-02-15",
        "linked_count": 0,
        "open_count": 0,
        "done_count": 0,
        "overdue_count": 0,
    }


def test_obligation_type_filter_works(client, auth_token, test_db):
    vat_entry(test_db)
    annual_entry(test_db)
    test_db.commit()

    response = client.get(
        f"{PATH}?include_empty=true&obligation_type=annual_report",
        headers=headers(auth_token),
    )

    assert response.status_code == 200
    assert [row["obligation_type"] for row in response.json()["items"]] == ["annual_report"]


def test_year_range_filter_works(client, auth_token, test_db):
    for year in (2025, 2026):
        vat_entry(test_db, year)
    test_db.commit()

    response = client.get(
        f"{PATH}?include_empty=true&tax_year_after=2026&tax_year_before=2026",
        headers=headers(auth_token),
    )

    assert response.status_code == 200
    assert [row["tax_year"] for row in response.json()["items"]] == [2026]


def test_groups_are_paginated(client, auth_token, test_db):
    for year in (2025, 2026):
        vat_entry(test_db, year)
    test_db.commit()

    response = client.get(
        f"{PATH}?include_empty=true&page=2&page_size=1",
        headers=headers(auth_token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 2
    assert payload["page_size"] == 1
    assert payload["total"] == 2
    assert [row["tax_year"] for row in payload["items"]] == [2026]


def test_client_record_id_filter_limits_group_counts(client, auth_token, test_db, test_user):
    entry = vat_entry(test_db)
    first_item = add_vat_item(test_db, entry, test_user.id)
    add_vat_item(test_db, entry, test_user.id)
    test_db.commit()

    response = client.get(
        f"{PATH}?client_record_id={first_item.client_record_id}",
        headers=headers(auth_token),
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["tax_calendar_entry_id"] == entry.id
    assert response.json()["items"][0]["linked_count"] == 1


def test_soft_deleted_client_rows_are_excluded_from_group_counts(
    client, auth_token, test_db, test_user
):
    vat = vat_entry(test_db)
    advance = advance_entry(test_db)
    annual = annual_entry(test_db)
    vat_item = add_vat_item(test_db, vat, test_user.id)
    advance_payment = add_advance_payment(test_db, advance)
    annual_report = add_annual_report(test_db, annual)
    test_db.get(ClientRecord, vat_item.client_record_id).deleted_at = utcnow()
    test_db.get(ClientRecord, advance_payment.client_record_id).deleted_at = utcnow()
    test_db.get(ClientRecord, annual_report.client_record_id).deleted_at = utcnow()
    test_db.commit()

    response = client.get(
        f"{PATH}?include_empty=true",
        headers=headers(auth_token),
    )

    assert response.status_code == 200
    linked_counts = {
        row["tax_calendar_entry_id"]: row["linked_count"] for row in response.json()["items"]
    }
    assert linked_counts == {
        vat.id: 0,
        advance.id: 0,
        annual.id: 0,
    }


def test_secretary_role_can_access(client, secretary_token, test_db):
    vat_entry(test_db)
    test_db.commit()

    response = client.get(
        f"{PATH}?include_empty=true",
        headers=headers(secretary_token),
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
