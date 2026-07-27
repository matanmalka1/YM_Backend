from __future__ import annotations

from datetime import date, datetime
from itertools import count
from typing import Any

from sqlalchemy.orm import Session

from app.reminders.models.reminder import Reminder, ReminderActionType, ReminderStatus
from app.tasks.models.task import Task, TaskPriority, TaskStatus
from app.users.models.user import User, UserRole
from tests.helpers.factory_utils import (
    ClientRef,
    resolve_exclusive,
)


class TaskFactory:
    """Model-level Task factory. Client stays unset unless the test asks for one."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._sequence = count(1)

    def __call__(
        self,
        *,
        title: str | None = None,
        description: str | None = None,
        status: TaskStatus = TaskStatus.OPEN,
        priority: TaskPriority = TaskPriority.NORMAL,
        due_date: date | None = None,
        assigned_to: User | None = None,
        assigned_to_user_id: int | None = None,
        assigned_role: UserRole | None = None,
        source_domain: str | None = None,
        source_id: int | None = None,
        client: ClientRef | None = None,
        client_record_id: int | None = None,
        action_key: str | None = None,
        action_payload: dict[str, Any] | None = None,
        created_by_user_id: int | None = None,
        completed_by_user_id: int | None = None,
        completed_at: datetime | None = None,
        canceled_by_user_id: int | None = None,
        canceled_at: datetime | None = None,
        deleted_at: datetime | None = None,
        commit: bool = False,
    ) -> Task:
        resolve_exclusive(client, client_record_id, names="client or client_record_id")
        resolve_exclusive(
            assigned_to, assigned_to_user_id, names="assigned_to or assigned_to_user_id"
        )
        sequence = next(self._sequence)
        task = Task(
            title=title or f"Test Task {sequence}",
            description=description,
            status=status,
            priority=priority,
            due_date=due_date,
            assigned_to_user_id=(
                assigned_to_user_id
                if assigned_to_user_id is not None
                else getattr(assigned_to, "id", None)
            ),
            assigned_role=assigned_role,
            source_domain=source_domain,
            source_id=source_id,
            client_record_id=(
                client_record_id if client_record_id is not None else getattr(client, "id", None)
            ),
            action_key=action_key,
            action_payload=action_payload,
            created_by_user_id=created_by_user_id,
            completed_by_user_id=completed_by_user_id,
            completed_at=completed_at,
            canceled_by_user_id=canceled_by_user_id,
            canceled_at=canceled_at,
            deleted_at=deleted_at,
        )
        self.db.add(task)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(task)
        return task


class ReminderFactory:
    """Model-level Reminder factory."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def __call__(
        self,
        *,
        fire_at: datetime,
        action_type: ReminderActionType = ReminderActionType.SEND_NOTIFICATION,
        status: ReminderStatus = ReminderStatus.SCHEDULED,
        source_domain: str | None = None,
        source_id: int | None = None,
        target_task_id: int | None = None,
        notification_template_key: str | None = None,
        payload: dict[str, Any] | None = None,
        created_by_user_id: int | None = None,
        fired_at: datetime | None = None,
        failure_reason: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        commit: bool = False,
    ) -> Reminder:
        fields: dict[str, Any] = {
            "fire_at": fire_at,
            "action_type": action_type,
            "status": status,
            "source_domain": source_domain,
            "source_id": source_id,
            "target_task_id": target_task_id,
            "notification_template_key": notification_template_key,
            "payload": payload,
            "created_by_user_id": created_by_user_id,
            "fired_at": fired_at,
            "failure_reason": failure_reason,
        }
        if created_at is not None:
            fields["created_at"] = created_at
        if updated_at is not None:
            fields["updated_at"] = updated_at
        reminder = Reminder(**fields)
        self.db.add(reminder)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(reminder)
        return reminder
