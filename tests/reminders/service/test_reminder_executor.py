from sqlalchemy import func, select

from app.audit.audit_constants import (
    ACTION_REMINDER_FAILED,
    ACTION_REMINDER_FIRED,
    ENTITY_REMINDER,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.notifications.schemas.notification_schemas import NotificationResult
from app.reminders.models.reminder import ReminderActionType, ReminderStatus
from app.reminders.schemas.reminder import ReminderCreateRequest
from app.reminders.services.reminder_executor_service import ReminderExecutorService
from app.reminders.services.reminder_service import ReminderService
from app.tasks.models.task import Task
from app.utils.time_utils import utcnow
from tests.helpers.identity import seed_client_identity


def _create_due_reminder(test_db, *, action_type, **kwargs):
    reminder = ReminderService(test_db).create_from_request(
        ReminderCreateRequest(
            fire_at=utcnow(),
            action_type=action_type,
            **kwargs,
        ),
        created_by_user_id=7,
    )
    test_db.commit()
    return reminder


def _reminder_audit(test_db, reminder_id: int, action: str) -> EntityAuditLog:
    return test_db.scalars(
        select(EntityAuditLog).where(
            EntityAuditLog.entity_type == ENTITY_REMINDER,
            EntityAuditLog.entity_id == reminder_id,
            EntityAuditLog.action == action,
        )
    ).one()


def test_create_task_action_creates_task_and_marks_reminder_fired(test_db):
    reminder = _create_due_reminder(
        test_db,
        action_type=ReminderActionType.CREATE_TASK,
        payload={"task": {"title": "Follow up with client", "priority": "high"}},
    )

    result = ReminderExecutorService(test_db).fire_due()

    test_db.refresh(reminder)
    task = test_db.get(Task, reminder.target_task_id)
    assert result.processed == 1
    assert result.fired == 1
    assert result.failed == 0
    assert reminder.status == ReminderStatus.FIRED
    assert reminder.failure_reason is None
    assert task is not None
    assert task.title == "Follow up with client"
    assert task.created_by_user_id is None

    audit = _reminder_audit(test_db, reminder.id, ACTION_REMINDER_FIRED)
    assert audit.actor_type == "system"
    assert audit.actor_display_name == "מערכת"
    assert audit.metadata_json["target_task_id"] == task.id


def test_send_notification_action_uses_canonical_service_and_marks_fired(test_db, monkeypatch):
    calls = []

    def _send(
        _self,
        request,
        triggered_by,
        idempotency_key,
        actor_name=None,
        retry_failed=False,
    ):
        calls.append((request, triggered_by, idempotency_key, actor_name, retry_failed))
        return NotificationResult(status="sent", notification_id=91)

    monkeypatch.setattr(
        "app.notifications.services.notification_service.NotificationService.send",
        _send,
    )
    reminder = _create_due_reminder(
        test_db,
        action_type=ReminderActionType.SEND_NOTIFICATION,
        source_id=44,
        notification_template_key="payment_reminder",
        payload={"client_record_id": 12},
    )

    result = ReminderExecutorService(test_db).fire_due()

    test_db.refresh(reminder)
    assert result.fired == 1
    assert reminder.status == ReminderStatus.FIRED
    assert len(calls) == 1
    request, triggered_by, idempotency_key, actor_name, retry_failed = calls[0]
    assert request.client_record_id == 12
    assert request.entity_id == 44
    assert request.trigger.value == "payment_reminder"
    assert triggered_by is None
    assert idempotency_key == f"reminder:{reminder.id}:notification"
    assert actor_name == "מערכת"
    assert retry_failed is True


def test_create_task_and_notify_performs_both_actions(test_db, monkeypatch):
    sent = []
    client = seed_client_identity(
        test_db,
        full_name="Combined Reminder Client",
        id_number="REMEXEC001",
    )

    def _send(
        _self,
        request,
        triggered_by,
        idempotency_key,
        actor_name=None,
        retry_failed=False,
    ):
        sent.append((request, idempotency_key))
        return NotificationResult(status="sent", notification_id=92)

    monkeypatch.setattr(
        "app.notifications.services.notification_service.NotificationService.send",
        _send,
    )
    reminder = _create_due_reminder(
        test_db,
        action_type=ReminderActionType.CREATE_TASK_AND_NOTIFY,
        notification_template_key="client_general_message",
        payload={
            "client_record_id": client.id,
            "task": {"title": "Combined reminder task"},
            "notification": {"overrides": {"subject": "Reminder", "body": "Please respond"}},
        },
    )

    result = ReminderExecutorService(test_db).fire_due()

    test_db.refresh(reminder)
    assert result.fired == 1
    assert reminder.status == ReminderStatus.FIRED
    assert test_db.get(Task, reminder.target_task_id).title == "Combined reminder task"
    assert len(sent) == 1
    assert sent[0][0].overrides.subject == "Reminder"


def test_notification_failure_marks_reminder_failed_with_system_audit(test_db, monkeypatch):
    def _send(
        _self,
        request,
        triggered_by,
        idempotency_key,
        actor_name=None,
        retry_failed=False,
    ):
        return NotificationResult(status="failed", notification_id=93, reason="SMTP unavailable")

    monkeypatch.setattr(
        "app.notifications.services.notification_service.NotificationService.send",
        _send,
    )
    reminder = _create_due_reminder(
        test_db,
        action_type=ReminderActionType.SEND_NOTIFICATION,
        notification_template_key="client_general_message",
        payload={"client_record_id": 14},
    )

    result = ReminderExecutorService(test_db).fire_due()

    test_db.refresh(reminder)
    assert result.failed == 1
    assert reminder.status == ReminderStatus.FAILED
    assert reminder.failure_reason == "SMTP unavailable"
    audit = _reminder_audit(test_db, reminder.id, ACTION_REMINDER_FAILED)
    assert audit.actor_type == "system"
    assert audit.actor_display_name == "מערכת"
    assert audit.new_value["failure_reason"] == "SMTP unavailable"


def test_partial_failure_retry_reuses_task_and_notification_idempotency_key(test_db, monkeypatch):
    client = seed_client_identity(
        test_db,
        full_name="Retry Reminder Client",
        id_number="REMEXEC002",
    )
    statuses = iter(
        [
            NotificationResult(status="failed", notification_id=94, reason="temporary failure"),
            NotificationResult(status="sent", notification_id=95),
        ]
    )
    idempotency_keys = []

    def _send(
        _self,
        request,
        triggered_by,
        idempotency_key,
        actor_name=None,
        retry_failed=False,
    ):
        idempotency_keys.append(idempotency_key)
        return next(statuses)

    monkeypatch.setattr(
        "app.notifications.services.notification_service.NotificationService.send",
        _send,
    )
    reminder = _create_due_reminder(
        test_db,
        action_type=ReminderActionType.CREATE_TASK_AND_NOTIFY,
        notification_template_key="client_general_message",
        payload={
            "client_record_id": client.id,
            "task": {"title": "Retry-safe task"},
        },
    )
    executor = ReminderExecutorService(test_db)

    first = executor.fire_due()
    test_db.refresh(reminder)
    original_task_id = reminder.target_task_id
    assert first.failed == 1
    assert reminder.status == ReminderStatus.FAILED
    assert original_task_id is not None

    executor.reminder_repo.update_status(reminder.id, ReminderStatus.SCHEDULED)
    test_db.commit()
    second = executor.fire_due()

    test_db.refresh(reminder)
    task_count = test_db.scalar(select(func.count(Task.id)))
    assert second.fired == 1
    assert reminder.status == ReminderStatus.FIRED
    assert reminder.target_task_id == original_task_id
    assert task_count == 1
    assert idempotency_keys == [
        f"reminder:{reminder.id}:notification",
        f"reminder:{reminder.id}:notification",
    ]


def test_reexecuting_fired_reminder_is_a_noop(test_db, monkeypatch):
    calls = 0

    def _send(
        _self,
        request,
        triggered_by,
        idempotency_key,
        actor_name=None,
        retry_failed=False,
    ):
        nonlocal calls
        calls += 1
        return NotificationResult(status="sent", notification_id=96)

    monkeypatch.setattr(
        "app.notifications.services.notification_service.NotificationService.send",
        _send,
    )
    reminder = _create_due_reminder(
        test_db,
        action_type=ReminderActionType.SEND_NOTIFICATION,
        notification_template_key="client_general_message",
        payload={"client_record_id": 16},
    )
    executor = ReminderExecutorService(test_db)

    assert executor._execute(reminder, utcnow()) is True
    assert executor._execute(reminder, utcnow()) is True

    assert calls == 1
