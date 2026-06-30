from datetime import timedelta

from app.audit.audit_constants import ENTITY_CLIENT
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.core.pagination import MAX_PAGE_SIZE


def _seed_three_audit_entries(test_db, test_user, client_record):
    """Create three audit entries with deterministic ascending timestamps.

    Returns (first, second, third) ordered oldest → newest.
    """
    writer = EntityAuditWriter(test_db)
    name = test_user.full_name
    first = writer.record_update(
        ENTITY_CLIENT,
        client_record.id,
        test_user.id,
        new_value={"phone": "step-1"},
        actor_display_name=name,
        metadata_json={"client_record_id": client_record.id},
    )
    second = writer.record_update(
        ENTITY_CLIENT,
        client_record.id,
        test_user.id,
        new_value={"phone": "step-2"},
        actor_display_name=name,
        metadata_json={"client_record_id": client_record.id},
    )
    third = writer.record_update(
        ENTITY_CLIENT,
        client_record.id,
        test_user.id,
        new_value={"phone": "step-3"},
        actor_display_name=name,
        metadata_json={"client_record_id": client_record.id},
    )
    first.performed_at = third.performed_at - timedelta(minutes=2)
    second.performed_at = third.performed_at - timedelta(minutes=1)
    test_db.commit()
    return first, second, third


def test_actor_display_name_snapshot_survives_user_rename(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    """The immutable actor_display_name snapshot must not change when the user is
    renamed; only the live-join performed_by_name reflects the new name."""
    client_record, _business = create_client_with_business(id_number="AUDIT-RENAME")
    original_name = test_user.full_name
    EntityAuditWriter(test_db).record_update(
        ENTITY_CLIENT,
        client_record.id,
        test_user.id,
        new_value={"full_name": original_name},
        actor_display_name=original_name,
        metadata_json={"client_record_id": client_record.id},
    )
    test_db.commit()

    test_user.full_name = "שם חדש לגמרי"
    test_db.commit()

    response = client.get(f"/api/v1/audit/client/{client_record.id}", headers=advisor_headers)
    assert response.status_code == 200
    item = response.json()["items"][0]
    # Snapshot is frozen at write time...
    assert item["actor_display_name"] == original_name
    # ...while the live-join performed_by_name reflects the renamed user.
    assert item["performed_by_name"] == "שם חדש לגמרי"


def test_audit_endpoint_page_one_returns_newest_records(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    client_record, _business = create_client_with_business(id_number="AUDIT-001")
    _first, second, third = _seed_three_audit_entries(test_db, test_user, client_record)

    response = client.get(
        f"/api/v1/audit/client/{client_record.id}?page=1&page_size=2",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["page"] == 1
    assert payload["page_size"] == 2
    # Newest first: page 1 holds the two most recent entries.
    assert [item["id"] for item in payload["items"]] == [third.id, second.id]
    assert all(item["performed_by_name"] == test_user.full_name for item in payload["items"])


def test_audit_endpoint_page_two_returns_remaining_records(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    client_record, _business = create_client_with_business(id_number="AUDIT-002")
    first, _second, _third = _seed_three_audit_entries(test_db, test_user, client_record)

    response = client.get(
        f"/api/v1/audit/client/{client_record.id}?page=2&page_size=2",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["page"] == 2
    assert payload["page_size"] == 2
    # Page 2 holds the single remaining (oldest) entry.
    assert [item["id"] for item in payload["items"]] == [first.id]


def test_audit_endpoint_page_size_validation(client, advisor_headers):
    response = client.get(
        f"/api/v1/audit/client/55?page_size={MAX_PAGE_SIZE + 1}",
        headers=advisor_headers,
    )

    assert response.status_code == 422


def test_audit_endpoint_rejects_unknown_entity_type(client, advisor_headers):
    response = client.get("/api/v1/audit/not_supported/55", headers=advisor_headers)

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["message"] == "סוג ישות לא נתמך להיסטוריית שינויים"
    assert payload["error"]["code"] == "AUDIT.INVALID_ENTITY_TYPE"


def test_audit_endpoint_returns_404_for_missing_entity(client, advisor_headers):
    response = client.get("/api/v1/audit/client/999999", headers=advisor_headers)

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["message"] == "הישות המבוקשת לא נמצאה"
    assert payload["error"]["code"] == "AUDIT.ENTITY_NOT_FOUND"
