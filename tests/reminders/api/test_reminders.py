from datetime import timedelta

from app.reminders.models.reminder import ReminderActionType, ReminderStatus
from app.reminders.repositories.reminder_repository import ReminderRepository
from app.utils.time_utils import utcnow


def test_create_list_and_get_scheduler_reminder(client, advisor_headers):
    fire_at = (utcnow() + timedelta(hours=1)).isoformat()
    create_resp = client.post(
        "/api/v1/reminders",
        headers=advisor_headers,
        json={
            "fire_at": fire_at,
            "action_type": "send_notification",
            "source_domain": "charge",
            "source_id": 44,
            "notification_template_key": "charge_due",
            "payload": {"charge_id": 44},
        },
    )

    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["status"] == "scheduled"
    assert created["action_type"] == "send_notification"
    assert "message" not in created

    list_resp = client.get("/api/v1/reminders?status=scheduled", headers=advisor_headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1

    get_resp = client.get(f"/api/v1/reminders/{created['id']}", headers=advisor_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == created["id"]


def test_cancel_reminder_marks_scheduled_as_canceled(client, test_db, advisor_headers):
    reminder = ReminderRepository(test_db).create(
        fire_at=utcnow(),
        action_type=ReminderActionType.CREATE_TASK,
    )

    resp = client.post(f"/api/v1/reminders/{reminder.id}/cancel", headers=advisor_headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "canceled"
    assert ReminderRepository(test_db).get_by_id(reminder.id).status == ReminderStatus.CANCELED
