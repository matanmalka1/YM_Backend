"""Runtime shape tests for the notification list/detail DTO split.

- LIST rows omit detail-only routing/delivery/debug fields.
- GET /notifications/{id} returns the full NotificationResponse.
- GET /notifications/{id} returns 404 for a missing notification.
"""

from __future__ import annotations

from app.notifications.models.notification import (
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)
from app.notifications.repositories.notification_repository import NotificationRepository
from tests.helpers.identity import seed_client_identity

# Fields that live only on the full NotificationResponse, never on a list row.
DETAIL_ONLY_FIELDS = (
    "channel",
    "binder_id",
    "annual_report_id",
    "signature_request_id",
    "entity_type",
    "entity_id",
    "sent_at",
    "failed_at",
    "error_message",
    "retry_count",
    "triggered_by",
)


def _seed_notification(test_db, suffix: str):
    client = seed_client_identity(
        test_db,
        full_name=f"List Detail Split {suffix}",
        id_number=f"LDS-{suffix}",
        email=f"lds-{suffix}@example.com",
    )
    notification = NotificationRepository(test_db).create(
        client_record_id=client.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="client@example.com",
        content_snapshot="גוף ההודעה",
        subject_snapshot="נושא",
        status=NotificationStatus.PENDING,
    )
    test_db.commit()
    return notification


def test_list_rows_omit_detail_only_fields(client, test_db, advisor_headers):
    _seed_notification(test_db, "list")

    response = client.get("/api/v1/notifications", headers=advisor_headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert items, "expected at least one seeded notification row"
    row = items[0]
    for field in DETAIL_ONLY_FIELDS:
        assert field not in row, f"list row leaked detail-only field: {field}"
    # The row still carries what the list UI renders.
    assert "status" in row
    assert "content_snapshot" in row


def test_detail_endpoint_returns_full_response(client, test_db, advisor_headers):
    notification = _seed_notification(test_db, "detail")

    response = client.get(
        f"/api/v1/notifications/{notification.id}", headers=advisor_headers
    )

    assert response.status_code == 200
    body = response.json()
    for field in DETAIL_ONLY_FIELDS:
        assert field in body, f"detail response missing full field: {field}"


def test_detail_endpoint_returns_404_for_missing(client, advisor_headers):
    response = client.get("/api/v1/notifications/999999", headers=advisor_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOTIFICATION.NOT_FOUND"
