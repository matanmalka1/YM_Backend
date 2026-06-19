"""Filter coverage for GET /api/v1/audit/{entity_type}/{entity_id}."""

from datetime import timedelta

from app.audit.audit_constants import (
    ACTION_CREATED,
    ACTION_DELETED,
    ACTION_UPDATED,
    ENTITY_CLIENT,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter


def _seed_mixed_entries(test_db, user_a, user_b, client_record):
    """Seed entries with varied action, performer, and timestamp.

    Returns a dict of the created entries keyed by a label.
    """
    writer = EntityAuditWriter(test_db)
    created = writer.record_create(ENTITY_CLIENT, client_record.id, user_a.id)
    updated = writer.record_update(ENTITY_CLIENT, client_record.id, user_b.id, new_value={"x": 1})
    deleted = writer.record_delete(ENTITY_CLIENT, client_record.id, user_a.id)
    # Deterministic ascending timestamps: created < updated < deleted.
    base = deleted.performed_at
    created.performed_at = base - timedelta(minutes=2)
    updated.performed_at = base - timedelta(minutes=1)
    test_db.commit()
    return {"created": created, "updated": updated, "deleted": deleted}


def test_audit_filter_by_action(
    client, test_db, advisor_headers, test_user, secretary_user, create_client_with_business
):
    client_record, _ = create_client_with_business(id_number="AUDIT-F-001")
    entries = _seed_mixed_entries(test_db, test_user, secretary_user, client_record)

    response = client.get(
        f"/api/v1/audit/client/{client_record.id}?action={ACTION_UPDATED}",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["id"] for item in payload["items"]] == [entries["updated"].id]


def test_audit_filter_by_user_id(
    client, test_db, advisor_headers, test_user, secretary_user, create_client_with_business
):
    client_record, _ = create_client_with_business(id_number="AUDIT-F-002")
    entries = _seed_mixed_entries(test_db, test_user, secretary_user, client_record)

    response = client.get(
        f"/api/v1/audit/client/{client_record.id}?user_id={test_user.id}",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    # test_user performed created + deleted; newest (deleted) first.
    assert payload["total"] == 2
    assert [item["id"] for item in payload["items"]] == [
        entries["deleted"].id,
        entries["created"].id,
    ]


def test_audit_filter_created_after_and_before(
    client, test_db, advisor_headers, test_user, secretary_user, create_client_with_business
):
    client_record, _ = create_client_with_business(id_number="AUDIT-F-003")
    entries = _seed_mixed_entries(test_db, test_user, secretary_user, client_record)

    pivot = entries["updated"].performed_at

    after = client.get(
        f"/api/v1/audit/client/{client_record.id}?created_after={pivot.isoformat()}",
        headers=advisor_headers,
    )
    assert after.status_code == 200
    after_payload = after.json()
    # updated (== pivot, inclusive >=) and deleted (later).
    assert after_payload["total"] == 2
    assert [item["id"] for item in after_payload["items"]] == [
        entries["deleted"].id,
        entries["updated"].id,
    ]

    before = client.get(
        f"/api/v1/audit/client/{client_record.id}?created_before={pivot.isoformat()}",
        headers=advisor_headers,
    )
    assert before.status_code == 200
    before_payload = before.json()
    # created (earlier) and updated (== pivot, inclusive <=).
    assert before_payload["total"] == 2
    assert [item["id"] for item in before_payload["items"]] == [
        entries["updated"].id,
        entries["created"].id,
    ]


def test_audit_filters_combined_with_and(
    client, test_db, advisor_headers, test_user, secretary_user, create_client_with_business
):
    client_record, _ = create_client_with_business(id_number="AUDIT-F-004")
    entries = _seed_mixed_entries(test_db, test_user, secretary_user, client_record)

    # action=created AND user_id=test_user → only the create entry.
    response = client.get(
        f"/api/v1/audit/client/{client_record.id}?action={ACTION_CREATED}&user_id={test_user.id}",
        headers=advisor_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["id"] for item in payload["items"]] == [entries["created"].id]

    # action=created AND user_id=secretary_user → no rows (secretary did the update).
    none_resp = client.get(
        f"/api/v1/audit/client/{client_record.id}"
        f"?action={ACTION_CREATED}&user_id={secretary_user.id}",
        headers=advisor_headers,
    )
    assert none_resp.status_code == 200
    none_payload = none_resp.json()
    assert none_payload["total"] == 0
    assert none_payload["items"] == []


def test_audit_filter_no_match_returns_empty(
    client, test_db, advisor_headers, test_user, secretary_user, create_client_with_business
):
    client_record, _ = create_client_with_business(id_number="AUDIT-F-005")
    _seed_mixed_entries(test_db, test_user, secretary_user, client_record)

    response = client.get(
        f"/api/v1/audit/client/{client_record.id}?action={ACTION_DELETED}&user_id={secretary_user.id}",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 0
    assert payload["items"] == []


def test_audit_page_beyond_last_returns_empty_with_total(
    client, test_db, advisor_headers, test_user, secretary_user, create_client_with_business
):
    client_record, _ = create_client_with_business(id_number="AUDIT-F-006")
    _seed_mixed_entries(test_db, test_user, secretary_user, client_record)

    response = client.get(
        f"/api/v1/audit/client/{client_record.id}?page=99&page_size=20",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["page"] == 99
    assert payload["page_size"] == 20
    assert payload["items"] == []
