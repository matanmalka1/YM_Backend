"""Tests: notification events in timeline — sent/failed shown, skipped/pending excluded."""

from datetime import datetime
from types import SimpleNamespace

from app.notification.models.notification import (
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)
from app.timeline.services.timeline_notification_event_builders import (
    notification_failed_event,
    notification_sent_event,
)


def _make_notification(
    trigger: NotificationTrigger = NotificationTrigger.BINDER_READY_FOR_HANDOVER,
    status: NotificationStatus = NotificationStatus.SENT,
    sent_at: datetime | None = None,
    failed_at: datetime | None = None,
    created_at: datetime | None = None,
    notification_id: int = 42,
    binder_id: int | None = 7,
    error_message: str | None = None,
    channel: NotificationChannel = NotificationChannel.EMAIL,
    recipient: str | None = "test@example.com",
):
    return SimpleNamespace(
        id=notification_id,
        trigger=trigger,
        status=status,
        sent_at=sent_at,
        failed_at=failed_at,
        created_at=created_at or datetime(2026, 4, 1, 10, 0),
        binder_id=binder_id,
        channel=channel,
        recipient=recipient,
        error_message=error_message,
    )


# ── Builder unit tests ────────────────────────────────────────────────────────


def test_notification_sent_event_structure():
    sent_at = datetime(2026, 4, 1, 12, 30)
    n = _make_notification(sent_at=sent_at)

    event = notification_sent_event(n)

    assert event["event_type"] == "notification_sent"
    assert event["timestamp"] == sent_at
    assert event["binder_id"] == 7
    assert event["charge_id"] is None
    assert "נשלחה" in event["description"]
    assert event["metadata"]["notification_id"] == 42
    assert event["metadata"]["trigger"] == "binder_ready_for_handover"
    assert event["metadata"]["channel"] == "email"


def test_notification_sent_event_falls_back_to_created_at_when_no_sent_at():
    created = datetime(2026, 4, 1, 9, 0)
    n = _make_notification(sent_at=None, created_at=created)

    event = notification_sent_event(n)

    assert event["timestamp"] == created


def test_notification_failed_event_structure():
    failed_at = datetime(2026, 4, 2, 8, 0)
    n = _make_notification(
        status=NotificationStatus.FAILED,
        failed_at=failed_at,
        error_message="connection timeout",
    )

    event = notification_failed_event(n)

    assert event["event_type"] == "notification_failed"
    assert event["timestamp"] == failed_at
    assert "נכשלה" in event["description"]
    assert event["metadata"]["error_message"] == "connection timeout"


def test_notification_sent_event_trigger_label_in_description():
    n = _make_notification(trigger=NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER)

    event = notification_sent_event(n)

    assert "תזכורת אישור דוח שנתי" in event["description"]


# ── Integration: timeline excludes skipped/pending ───────────────────────────


def test_timeline_notification_events_only_sent_and_failed(test_db, test_user):
    """
    TimelineService._build_notification_events returns events only for SENT and FAILED.
    SKIPPED and PENDING are excluded.
    """
    from app.notification.models.notification import (
        Notification,
        NotificationChannel,
        NotificationStatus,
        NotificationTrigger,
    )
    from app.notification.repositories.notification_repository import NotificationRepository
    from app.timeline.services.timeline_notification_event_builders import (
        notification_failed_event,
        notification_sent_event,
    )
    from tests.helpers.identity import seed_client_identity

    client = seed_client_identity(test_db, full_name="Timeline Notif Client", id_number="TL-N-01")
    repo = NotificationRepository(test_db)

    sent_n = repo.create(
        client_record_id=client.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="a@b.com",
        content_snapshot="sent body",
        status=NotificationStatus.PENDING,
    )
    repo.mark_sent(sent_n.id)

    failed_n = repo.create(
        client_record_id=client.id,
        trigger=NotificationTrigger.BINDER_GENERAL_REMINDER,
        channel=NotificationChannel.EMAIL,
        recipient="a@b.com",
        content_snapshot="failed body",
        status=NotificationStatus.PENDING,
    )
    repo.mark_failed(failed_n.id, "smtp error")

    skipped_n = repo.create(
        client_record_id=client.id,
        trigger=NotificationTrigger.BINDER_READY_FOR_HANDOVER,
        channel=NotificationChannel.EMAIL,
        recipient=None,
        content_snapshot="skipped body",
        status=NotificationStatus.SKIPPED,
    )

    pending_n = repo.create(
        client_record_id=client.id,
        trigger=NotificationTrigger.CLIENT_DOCUMENTS_REQUEST,
        channel=NotificationChannel.EMAIL,
        recipient="a@b.com",
        content_snapshot="pending body",
        status=NotificationStatus.PENDING,
    )

    test_db.flush()

    # Call the private helper directly
    from app.timeline.services.timeline_service import TimelineService

    svc = TimelineService(test_db)
    events = svc._build_notification_events(client.id)

    event_types = {e["event_type"] for e in events}
    notification_ids_in_events = {e["metadata"]["notification_id"] for e in events}

    assert "notification_sent" in event_types
    assert "notification_failed" in event_types
    assert sent_n.id in notification_ids_in_events
    assert failed_n.id in notification_ids_in_events
    # Skipped and pending must NOT appear
    assert skipped_n.id not in notification_ids_in_events
    assert pending_n.id not in notification_ids_in_events
