from __future__ import annotations

import datetime as dt

from app.notification.models.notification import (
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)
from app.notification.repositories.notification_repository import NotificationRepository
from tests.helpers.identity import seed_client_identity


def _client(test_db, suffix: str):
    return seed_client_identity(
        test_db,
        full_name=f"Notifications Center {suffix}",
        id_number=f"NC-{suffix}",
        email=f"center-{suffix}@example.com",
    )


def _notification(
    test_db,
    client_record_id: int,
    *,
    trigger: NotificationTrigger = NotificationTrigger.CLIENT_GENERAL_MESSAGE,
    status: NotificationStatus = NotificationStatus.PENDING,
    triggered_by: int | None = None,
    created_at: dt.datetime | None = None,
):
    item = NotificationRepository(test_db).create(
        client_record_id=client_record_id,
        trigger=trigger,
        channel=NotificationChannel.EMAIL,
        recipient="client@example.com",
        content_snapshot="גוף ההודעה",
        subject_snapshot="נושא",
        status=status,
        triggered_by=triggered_by,
    )
    if created_at is not None:
        item.created_at = created_at
        test_db.flush()
    return item


def test_list_notifications_accepts_page_size_25(client, test_db, advisor_headers):
    seeded = _client(test_db, "page-size")
    _notification(test_db, seeded.id)
    test_db.commit()

    response = client.get("/api/v1/notifications?page_size=25", headers=advisor_headers)

    assert response.status_code == 200
    assert response.json()["page_size"] == 25


def test_list_notifications_accepts_page_size_50(client, test_db, advisor_headers):
    seeded = _client(test_db, "page-size-50")
    _notification(test_db, seeded.id)
    test_db.commit()

    response = client.get("/api/v1/notifications?page_size=50", headers=advisor_headers)

    assert response.status_code == 200
    assert response.json()["page_size"] == 50


def test_list_notifications_rejects_page_size_30(client, advisor_headers):
    response = client.get("/api/v1/notifications?page_size=30", headers=advisor_headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_list_notifications_openapi_page_size_contract_is_enum(client):
    schema = client.app.openapi()
    parameters = schema["paths"]["/api/v1/notifications"]["get"]["parameters"]
    page_size_schema = next(
        parameter["schema"] for parameter in parameters if parameter["name"] == "page_size"
    )
    if "$ref" in page_size_schema:
        schema_name = page_size_schema["$ref"].removeprefix("#/components/schemas/")
        page_size_schema = schema["components"]["schemas"][schema_name]

    assert page_size_schema["enum"] == [25, 50]
    assert "minimum" not in page_size_schema
    assert "maximum" not in page_size_schema


def test_trigger_filter_returns_only_matching_records(client, test_db, advisor_headers):
    seeded = _client(test_db, "trigger")
    wanted = _notification(
        test_db,
        seeded.id,
        trigger=NotificationTrigger.PAYMENT_REMINDER,
    )
    _notification(test_db, seeded.id, trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE)
    test_db.commit()

    resp = client.get(
        "/api/v1/notifications?trigger=payment_reminder",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == wanted.id


def test_status_filter_returns_only_matching_records(client, test_db, advisor_headers):
    seeded = _client(test_db, "status")
    wanted = _notification(test_db, seeded.id, status=NotificationStatus.SENT)
    _notification(test_db, seeded.id, status=NotificationStatus.FAILED)
    test_db.commit()

    resp = client.get("/api/v1/notifications?status=sent", headers=advisor_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == wanted.id


def test_date_from_date_to_boundaries(client, test_db, advisor_headers):
    seeded = _client(test_db, "dates")
    start = dt.datetime(2026, 1, 10, 9, 0, 0)
    end = dt.datetime(2026, 1, 20, 17, 0, 0)
    first = _notification(test_db, seeded.id, created_at=start)
    second = _notification(test_db, seeded.id, created_at=end)
    _notification(test_db, seeded.id, created_at=start - dt.timedelta(seconds=1))
    _notification(test_db, seeded.id, created_at=end + dt.timedelta(seconds=1))
    test_db.commit()

    resp = client.get(
        "/api/v1/notifications?date_from=2026-01-10T09:00:00&date_to=2026-01-20T17:00:00",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert {item["id"] for item in data["items"]} == {first.id, second.id}


def test_triggered_by_filter(client, test_db, advisor_headers):
    seeded = _client(test_db, "triggered")
    wanted = _notification(test_db, seeded.id, triggered_by=10)
    _notification(test_db, seeded.id, triggered_by=20)
    test_db.commit()

    resp = client.get("/api/v1/notifications?triggered_by=10", headers=advisor_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == wanted.id


def test_empty_result_returns_empty_page(client, advisor_headers):
    resp = client.get("/api/v1/notifications?status=sent", headers=advisor_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []
