from __future__ import annotations

from sqlalchemy.orm import Session

from app.clients.repositories.client_identity_repository import ClientIdentityRepository
from app.common.source_types import WorkQueueSourceType, normalize_source_domain
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, NotFoundError
from app.reminders.models.reminder import Reminder, ReminderStatus
from app.reminders.repositories.reminder_repository import ReminderRepository
from app.reminders.schemas.reminder import ReminderCreateRequest, ReminderResponse
from app.tasks.repositories.task_repository import TaskRepository
from app.work_queue.services.work_queue_source_lookup import load_source_states


class ReminderService:
    def __init__(self, db: Session):
        self.db = db
        self.reminder_repo = ReminderRepository(db)
        self.client_identity_repo = ClientIdentityRepository(db)
        self.task_repo = TaskRepository(db)

    def create_from_request(
        self, request: ReminderCreateRequest, *, created_by_user_id: int
    ) -> Reminder:
        return self.reminder_repo.create(
            fire_at=request.fire_at,
            action_type=request.action_type,
            source_domain=request.source_domain,
            source_id=request.source_id,
            target_task_id=request.target_task_id,
            notification_template_key=request.notification_template_key,
            payload=request.payload,
            created_by_user_id=created_by_user_id,
        )

    def get_reminders(
        self, *, status: str | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[Reminder], int]:
        status_enum = self._parse_status(status)
        items = self.reminder_repo.list_by_status(status_enum, page, page_size)
        total = self.reminder_repo.count_by_status(status_enum)
        return items, total

    def get_reminder(self, reminder_id: int) -> Reminder | None:
        return self.reminder_repo.get_by_id(reminder_id)

    def cancel_reminder(self, reminder_id: int) -> Reminder:
        reminder = self.reminder_repo.get_by_id(reminder_id)
        if reminder is None:
            raise NotFoundError("התזכורת לא נמצאה", ErrorCode.REMINDER_NOT_FOUND)
        if reminder.status != ReminderStatus.SCHEDULED:
            raise AppError(
                "ניתן לבטל רק טריגר מתוזמן",
                ErrorCode.REMINDER_INVALID_STATUS,
            )
        return self.reminder_repo.update_status(reminder_id, ReminderStatus.CANCELED)

    def to_response(self, reminder: Reminder) -> ReminderResponse:
        return self.to_responses([reminder])[0]

    def to_responses(self, reminders: list[Reminder]) -> list[ReminderResponse]:
        client_by_reminder_id = self._resolve_client_record_ids(reminders)
        client_ids = [
            client_record_id
            for client_record_id in client_by_reminder_id.values()
            if client_record_id is not None
        ]
        profiles = self.client_identity_repo.get_display_map(client_ids)

        responses = []
        for reminder in reminders:
            client_record_id = client_by_reminder_id.get(reminder.id)
            profile = profiles.get(client_record_id)
            response = ReminderResponse.model_validate(reminder)
            response.client_record_id = client_record_id
            response.client_name = profile.client_name if profile else None
            response.office_client_number = profile.office_client_number if profile else None
            responses.append(response)
        return responses

    def _resolve_client_record_ids(self, reminders: list[Reminder]) -> dict[int, int | None]:
        resolved: dict[int, int | None] = {}
        source_keys_by_reminder_id: dict[int, tuple[WorkQueueSourceType, int]] = {}
        target_task_ids: set[int] = set()

        for reminder in reminders:
            payload_client_id = self._payload_client_record_id(reminder)
            if payload_client_id is not None:
                resolved[reminder.id] = payload_client_id
                continue

            source_type = normalize_source_domain(reminder.source_domain)
            if source_type is not None and reminder.source_id is not None:
                source_keys_by_reminder_id[reminder.id] = (
                    source_type,
                    reminder.source_id,
                )

            if reminder.target_task_id is not None:
                target_task_ids.add(reminder.target_task_id)

        task_source_keys_by_reminder_id: dict[int, tuple[WorkQueueSourceType, int]] = {}
        if target_task_ids:
            tasks_by_id = {task.id: task for task in self.task_repo.list_by_ids(target_task_ids)}
            for reminder in reminders:
                if reminder.id in resolved or reminder.id in source_keys_by_reminder_id:
                    continue
                if reminder.target_task_id is None:
                    continue
                task = tasks_by_id.get(reminder.target_task_id)
                if task is None or task.source_id is None:
                    continue
                source_type = normalize_source_domain(task.source_domain)
                if source_type is not None:
                    task_source_keys_by_reminder_id[reminder.id] = (
                        source_type,
                        task.source_id,
                    )

        source_keys = set(source_keys_by_reminder_id.values()) | set(
            task_source_keys_by_reminder_id.values()
        )
        source_states = load_source_states(self.db, source_keys)

        for reminder in reminders:
            if reminder.id in resolved:
                continue
            source_key = source_keys_by_reminder_id.get(reminder.id)
            if source_key is None:
                source_key = task_source_keys_by_reminder_id.get(reminder.id)
            if source_key is None:
                resolved[reminder.id] = None
                continue
            state = source_states.get((source_key[0].value, source_key[1]))
            resolved[reminder.id] = state.client_record_id if state else None

        return resolved

    @staticmethod
    def _payload_client_record_id(reminder: Reminder) -> int | None:
        payload = reminder.payload or {}
        raw = payload.get("client_record_id")
        if raw is None:
            return None
        try:
            return int(raw)
        except TypeError, ValueError:
            return None

    def _parse_status(self, status: str | None) -> ReminderStatus:
        if status is None:
            return ReminderStatus.SCHEDULED
        valid_statuses = {item.value for item in ReminderStatus}
        if status not in valid_statuses:
            raise AppError(
                f"סטטוס לא חוקי: {status}. חייב להיות אחד מהבאים: {', '.join(valid_statuses)}",
                ErrorCode.REMINDER_INVALID_STATUS,
            )
        return ReminderStatus(status)
