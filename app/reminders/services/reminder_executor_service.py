from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.audit.audit_constants import (
    ACTION_REMINDER_FAILED,
    ACTION_REMINDER_FIRED,
    ENTITY_REMINDER,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.notifications.models.notification import NotificationTrigger
from app.notifications.schemas.notification_schemas import NotificationSendRequest
from app.notifications.services.notification_service import NotificationService
from app.reminders.models.reminder import (
    Reminder,
    ReminderActionType,
    ReminderStatus,
)
from app.reminders.repositories.reminder_repository import ReminderRepository
from app.reminders.services.reminder_service import ReminderService
from app.tasks.schemas.task import TaskCreateRequest
from app.tasks.services.task_service import TaskService
from app.utils.time_utils import utcnow

_SYSTEM_ACTOR_DISPLAY = "מערכת"
_TASK_PAYLOAD_FIELDS = frozenset(TaskCreateRequest.model_fields)


@dataclass(frozen=True)
class ReminderExecutionResult:
    processed: int
    fired: int
    failed: int


class ReminderExecutorService:
    def __init__(self, db: Session):
        self.db = db
        self.reminder_repo = ReminderRepository(db)
        self.reminder_service = ReminderService(db)
        self.task_service = TaskService(db)
        self.notification_service = NotificationService(db)
        self._audit = EntityAuditWriter(db)

    def _audit_metadata(self, reminder: Reminder) -> dict:
        payload = reminder.payload or {}
        meta = {
            "client_record_id": payload.get("client_record_id"),
            "source_domain": reminder.source_domain,
            "source_id": reminder.source_id,
            "target_task_id": reminder.target_task_id,
            "action_type": reminder.action_type,
        }
        return {key: value for key, value in meta.items() if value is not None}

    def fire_due(self, *, now: datetime | None = None, limit: int = 100) -> ReminderExecutionResult:
        now = now or utcnow()
        reminders = self.reminder_repo.list_due_scheduled(now, limit=limit)
        fired = 0
        failed = 0
        for reminder in reminders:
            if self._execute(reminder, now):
                fired += 1
            else:
                failed += 1
        return ReminderExecutionResult(
            processed=len(reminders),
            fired=fired,
            failed=failed,
        )

    def _execute(self, reminder: Reminder, now: datetime) -> bool:
        if reminder.status == ReminderStatus.FIRED:
            return True
        if reminder.status == ReminderStatus.CANCELED:
            return False

        reminder_id = reminder.id
        old_status = reminder.status
        try:
            self._dispatch(reminder)
            updated = self.reminder_repo.update_status(
                reminder_id,
                ReminderStatus.FIRED,
                fired_at=now,
                failure_reason=None,
            )
            if updated is None:
                raise RuntimeError("התזכורת לא נמצאה לאחר ביצוע הפעולה")
            self._audit.record_action(
                ENTITY_REMINDER,
                updated.id,
                None,
                ACTION_REMINDER_FIRED,
                old_value={"status": old_status},
                new_value={"status": updated.status},
                actor_type="system",
                actor_display_name=_SYSTEM_ACTOR_DISPLAY,
                metadata_json=self._audit_metadata(updated),
            )
            self.db.commit()
            return True
        except Exception as exc:
            self.db.rollback()
            return self._mark_failed(reminder_id, old_status, now, exc)

    def _dispatch(self, reminder: Reminder) -> None:
        if reminder.action_type == ReminderActionType.CREATE_TASK:
            self._ensure_task(reminder)
            return
        if reminder.action_type == ReminderActionType.SEND_NOTIFICATION:
            self._send_notification(reminder)
            return
        if reminder.action_type == ReminderActionType.CREATE_TASK_AND_NOTIFY:
            self._ensure_task(reminder)
            self._send_notification(reminder)
            return
        raise ValueError(f"סוג פעולה לא נתמך: {reminder.action_type}")

    def _ensure_task(self, reminder: Reminder) -> None:
        if reminder.target_task_id is not None:
            self.task_service.get(reminder.target_task_id)
            return

        task = self.task_service.create_in_transaction(
            self._task_request(reminder),
            created_by_user_id=None,
            actor_name=_SYSTEM_ACTOR_DISPLAY,
        )
        reminder.target_task_id = task.id
        self.db.commit()

    def _task_request(self, reminder: Reminder) -> TaskCreateRequest:
        payload = reminder.payload or {}
        nested = payload.get("task")
        if nested is not None and not isinstance(nested, dict):
            raise ValueError("payload.task חייב להיות אובייקט")
        raw: dict[str, Any] = (
            dict(nested)
            if isinstance(nested, dict)
            else {key: payload[key] for key in _TASK_PAYLOAD_FIELDS if key in payload}
        )
        if reminder.source_domain is not None:
            raw.setdefault("source_domain", reminder.source_domain)
        if reminder.source_id is not None:
            raw.setdefault("source_id", reminder.source_id)
        if "client_record_id" in payload:
            raw.setdefault("client_record_id", payload["client_record_id"])
        try:
            return TaskCreateRequest.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(f"payload המשימה אינו תקין: {exc}") from exc

    def _send_notification(self, reminder: Reminder) -> None:
        result = self.notification_service.send(
            self._notification_request(reminder),
            triggered_by=None,
            idempotency_key=f"reminder:{reminder.id}:notification",
            actor_name=_SYSTEM_ACTOR_DISPLAY,
            retry_failed=True,
        )
        if result.status != "sent":
            reason = result.reason or f"סטטוס הודעה: {result.status}"
            raise RuntimeError(reason)

    def _notification_request(self, reminder: Reminder) -> NotificationSendRequest:
        if not reminder.notification_template_key:
            raise ValueError("חסר notification_template_key")
        try:
            trigger = NotificationTrigger(reminder.notification_template_key)
        except ValueError as exc:
            raise ValueError(
                f"notification_template_key לא חוקי: {reminder.notification_template_key}"
            ) from exc

        payload = reminder.payload or {}
        nested = payload.get("notification")
        if nested is not None and not isinstance(nested, dict):
            raise ValueError("payload.notification חייב להיות אובייקט")
        values = dict(nested) if isinstance(nested, dict) else {}
        client_record_id = values.get("client_record_id")
        if client_record_id is None:
            client_record_id = self.reminder_service.to_response(reminder).client_record_id
        if client_record_id is None:
            raise ValueError("לא ניתן לזהות לקוח עבור ההתראה")

        entity_id = values.get("entity_id", reminder.source_id)
        request_data = {
            "client_record_id": client_record_id,
            "trigger": trigger,
            "entity_id": entity_id,
            "business_id": values.get("business_id"),
            "channel": values.get("channel"),
            "overrides": values.get("overrides"),
            "confirm_recent_duplicate": values.get("confirm_recent_duplicate", False),
        }
        try:
            return NotificationSendRequest.model_validate(request_data)
        except ValidationError as exc:
            raise ValueError(f"payload ההתראה אינו תקין: {exc}") from exc

    def _mark_failed(
        self,
        reminder_id: int,
        old_status: ReminderStatus,
        now: datetime,
        error: Exception,
    ) -> bool:
        reason = str(error).strip() or error.__class__.__name__
        updated = self.reminder_repo.update_status(
            reminder_id,
            ReminderStatus.FAILED,
            fired_at=now,
            failure_reason=reason,
        )
        if updated is None:
            raise RuntimeError("התזכורת לא נמצאה לאחר כשל בביצוע") from error
        self._audit.record_action(
            ENTITY_REMINDER,
            updated.id,
            None,
            ACTION_REMINDER_FAILED,
            old_value={"status": old_status},
            new_value={"status": updated.status, "failure_reason": updated.failure_reason},
            actor_type="system",
            actor_display_name=_SYSTEM_ACTOR_DISPLAY,
            metadata_json=self._audit_metadata(updated),
        )
        self.db.commit()
        return False
