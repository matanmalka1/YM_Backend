from __future__ import annotations

import datetime as dt

from app.notifications.models.notification import (
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)


def _client(client_factory, suffix: str):
    return client_factory(
        full_name=f"Notifications Center {suffix}",
        id_number=f"NC-{suffix}",
        email=f"center-{suffix}@example.com",
    )


def _notification(
    notification_factory,
    client_record_id: int,
    *,
    trigger: NotificationTrigger = NotificationTrigger.CLIENT_GENERAL_MESSAGE,
    status: NotificationStatus = NotificationStatus.PENDING,
    triggered_by: int | None = None,
    created_at: dt.datetime | None = None,
):
    return notification_factory(
        client_record_id=client_record_id,
        trigger=trigger,
        channel=NotificationChannel.EMAIL,
        recipient="client@example.com",
        content_snapshot="גוף ההודעה",
        subject_snapshot="נושא",
        status=status,
        triggered_by=triggered_by,
        created_at=created_at,
    )


def test_list_notifications_accepts_page_size_25(
    client, test_db, advisor_headers, client_factory, notification_factory
):
    seeded = _client(client_factory, "page-size")
    _notification(notification_factory, seeded.id)
    test_db.commit()

    response = client.get("/api/v1/notifications?page_size=25", headers=advisor_headers)

    assert response.status_code == 200
    assert response.json()["page_size"] == 25


def test_notification_metadata_is_backend_owned_and_available_to_operational_roles(
    client, advisor_headers, secretary_headers
):
    for headers in (advisor_headers, secretary_headers):
        response = client.get("/api/v1/notifications/metadata", headers=headers)
        assert response.status_code == 200
        options = {item["value"]: item for item in response.json()["triggers"]}
        assert options["vat_documents_reminder"] == {
            "value": "vat_documents_reminder",
            "label": "תזכורת מסמכי מע״מ",
            "domain_label": "מע״מ",
            "client_level_manual": False,
        }
        assert options["client_general_message"]["client_level_manual"] is True


def test_trigger_filter_returns_only_matching_records(
    client, test_db, advisor_headers, client_factory, notification_factory
):
    seeded = _client(client_factory, "trigger")
    wanted = _notification(
        notification_factory,
        seeded.id,
        trigger=NotificationTrigger.PAYMENT_REMINDER,
    )
    _notification(
        notification_factory, seeded.id, trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE
    )
    test_db.commit()

    resp = client.get(
        "/api/v1/notifications?trigger=payment_reminder",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == wanted.id


def test_status_filter_returns_only_matching_records(
    client, test_db, advisor_headers, client_factory, notification_factory
):
    seeded = _client(client_factory, "status")
    wanted = _notification(notification_factory, seeded.id, status=NotificationStatus.SENT)
    _notification(notification_factory, seeded.id, status=NotificationStatus.FAILED)
    test_db.commit()

    resp = client.get("/api/v1/notifications?status=sent", headers=advisor_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == wanted.id


def test_created_after_created_before_boundaries(
    client, test_db, advisor_headers, client_factory, notification_factory
):
    seeded = _client(client_factory, "dates")
    start = dt.datetime(2026, 1, 10, 9, 0, 0)
    end = dt.datetime(2026, 1, 20, 17, 0, 0)
    first = _notification(notification_factory, seeded.id, created_at=start)
    second = _notification(notification_factory, seeded.id, created_at=end)
    _notification(notification_factory, seeded.id, created_at=start - dt.timedelta(seconds=1))
    _notification(notification_factory, seeded.id, created_at=end + dt.timedelta(seconds=1))
    test_db.commit()

    resp = client.get(
        "/api/v1/notifications?created_after=2026-01-10T09:00:00&created_before=2026-01-20T17:00:00",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert {item["id"] for item in data["items"]} == {first.id, second.id}


def test_old_date_params_are_ignored(
    client, test_db, advisor_headers, client_factory, notification_factory
):
    """Old date_from/date_to are not part of the contract and must not filter."""
    seeded = _client(client_factory, "olddates")
    _notification(notification_factory, seeded.id, created_at=dt.datetime(2026, 1, 10, 9, 0, 0))
    _notification(notification_factory, seeded.id, created_at=dt.datetime(2026, 1, 20, 17, 0, 0))
    test_db.commit()

    resp = client.get(
        "/api/v1/notifications?date_from=2026-06-01T00:00:00&date_to=2026-06-30T00:00:00",
        headers=advisor_headers,
    )

    # Unknown params are ignored by FastAPI: no filtering applied.
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_triggered_by_filter(
    client, test_db, advisor_headers, client_factory, notification_factory, actor_user
):
    seeded = _client(client_factory, "triggered")
    wanted = _notification(notification_factory, seeded.id, triggered_by=actor_user.id)
    _notification(notification_factory, seeded.id, triggered_by=actor_user.id)
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
