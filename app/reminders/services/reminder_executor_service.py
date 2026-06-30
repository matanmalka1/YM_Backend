from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.audit.audit_constants import ACTION_REMINDER_FAILED, ENTITY_REMINDER
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.reminders.models.reminder import (
    Reminder,
    ReminderActionType,
    ReminderStatus,
)
from app.reminders.repositories.reminder_repository import ReminderRepository
from app.utils.time_utils import utcnow


@dataclass(frozen=True)
class ReminderExecutionResult:
    processed: int
    fired: int
    failed: int


class ReminderExecutorService:
    def __init__(self, db: Session):
        self.db = db
        self.reminder_repo = ReminderRepository(db)
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
        reason = self._unsupported_reason(reminder.action_type)
        old_status = reminder.status
        updated = self.reminder_repo.update_status(
            reminder.id,
            ReminderStatus.FAILED,
            fired_at=now,
            failure_reason=reason,
        )
        if updated is not None:
            self._audit.record_action(
                ENTITY_REMINDER,
                updated.id,
                None,
                ACTION_REMINDER_FAILED,
                old_value={"status": old_status},
                new_value={"status": updated.status, "failure_reason": updated.failure_reason},
                actor_type="system",
                actor_display_name="מערכת",
                metadata_json=self._audit_metadata(updated),
            )
        return False

    def _unsupported_reason(self, action_type: ReminderActionType) -> str:
        if action_type == ReminderActionType.CREATE_TASK:
            return "ביצוע CREATE_TASK עדיין לא ממומש: ממתין למודל Task persisted"
        if action_type == ReminderActionType.CREATE_TASK_AND_NOTIFY:
            return "ביצוע CREATE_TASK_AND_NOTIFY עדיין לא ממומש: ממתין ל-Task ולתזמור פעולות"
        return "ביצוע SEND_NOTIFICATION עדיין לא ממומש: ממתין לחיבור NotificationService נקי"
