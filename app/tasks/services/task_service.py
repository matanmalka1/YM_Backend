from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import AdvancePayment
from app.annual_reports.models.annual_report_model import AnnualReport
from app.binders.models.binder import Binder
from app.charges.models.charge import Charge
from app.common.services.base_service import BaseService
from app.common.source_types import WorkQueueSourceType, normalize_source_domain
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.tasks.models.task import Task, TaskPriority, TaskStatus
from app.tasks.repositories.task_repository import TaskRepository
from app.tasks.schemas.task import (
    TaskBulkActionResponse,
    TaskBulkFailure,
    TaskCreateRequest,
    TaskUpdateRequest,
)
from app.tasks.services.source_validator import source_exists
from app.users.models.user import UserRole
from app.utils.time_utils import utcnow
from app.vat.models.vat_work_item import VatWorkItem

_TERMINAL = {TaskStatus.DONE, TaskStatus.CANCELED}

_NOT_FOUND = ErrorCode.TASK_NOT_FOUND
_CONFLICT = ErrorCode.TASK_CONFLICT
_INVALID_SOURCE = ErrorCode.TASK_INVALID_SOURCE
_INVALID_ASSIGNEE = ErrorCode.TASK_INVALID_ASSIGNEE
_CLIENT_SOURCE_MISMATCH = ErrorCode.TASK_CLIENT_SOURCE_MISMATCH

_SOURCE_CLIENT_MAP: dict[WorkQueueSourceType, type] = {
    WorkQueueSourceType.VAT_WORK_ITEM: VatWorkItem,
    WorkQueueSourceType.ANNUAL_REPORT: AnnualReport,
    WorkQueueSourceType.ADVANCE_PAYMENT: AdvancePayment,
    WorkQueueSourceType.CHARGE: Charge,
    WorkQueueSourceType.BINDER: Binder,
}


class TaskService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db)
        self.repo = TaskRepository(db)

    def create(self, data: TaskCreateRequest, created_by_user_id: int | None) -> Task:
        self._validate_source(data.source_domain, data.source_id)
        resolved_client_id = self._resolve_client_from_source(data.source_domain, data.source_id)
        if data.client_record_id is not None:
            if resolved_client_id is not None and resolved_client_id != data.client_record_id:
                raise AppError("מקור המשימה אינו שייך ללקוח שצוין", _CLIENT_SOURCE_MISMATCH)
            self._validate_client_exists(data.client_record_id)
            final_client_id = data.client_record_id
        else:
            final_client_id = resolved_client_id
        with self.transaction():
            return self.repo.create(
                title=data.title,
                created_by_user_id=created_by_user_id,
                description=data.description,
                priority=data.priority,
                due_date=data.due_date,
                assigned_to_user_id=data.assigned_to_user_id,
                assigned_role=data.assigned_role,
                source_domain=data.source_domain,
                source_id=data.source_id,
                client_record_id=final_client_id,
                action_key=data.action_key,
                action_payload=data.action_payload,
            )

    def list(
        self,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assigned_to_user_id: int | None = None,
        assigned_role: UserRole | None = None,
        source_domain: WorkQueueSourceType | None = None,
        source_id: int | None = None,
        due_before=None,
        due_after=None,
        page: int = 1,
        page_size: int = 20,
    ):
        return self.repo.list_active(
            status=status,
            priority=priority,
            assigned_to_user_id=assigned_to_user_id,
            assigned_role=assigned_role,
            source_domain=source_domain,
            source_id=source_id,
            due_before=due_before,
            due_after=due_after,
            page=page,
            page_size=page_size,
        )

    def list_by_client(
        self,
        client_record_id: int,
        status: TaskStatus | None = None,
        assigned_to_user_id: int | None = None,
        source_domain: WorkQueueSourceType | None = None,
        due_before=None,
        due_after=None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Task], int]:
        self._validate_client_exists(client_record_id)
        return self.repo.list_by_client_id(
            client_record_id=client_record_id,
            status=status,
            assigned_to_user_id=assigned_to_user_id,
            source_domain=source_domain,
            due_before=due_before,
            due_after=due_after,
            page=page,
            page_size=page_size,
        )

    def update(self, task_id: int, data: TaskUpdateRequest) -> Task:
        task = self.get(task_id)
        if task.status in _TERMINAL:
            raise ConflictError("לא ניתן לערוך משימה שהושלמה או בוטלה", _CONFLICT)
        updates = data.model_dump(exclude_unset=True)
        if "source_domain" in updates or "source_id" in updates:
            updates = self._resolve_source_update(updates)
        with self.transaction():
            for field, value in updates.items():
                setattr(task, field, value)
            task.updated_at = utcnow()
        return task

    def _resolve_source_update(self, updates: dict[str, Any]) -> dict[str, Any]:
        has_domain = "source_domain" in updates
        has_id = "source_id" in updates
        if has_domain != has_id:
            raise AppError(
                "קישור מקור למשימה חייב לכלול סוג מקור ומזהה מקור",
                _INVALID_SOURCE,
            )

        new_domain = updates["source_domain"]
        new_id = updates["source_id"]
        clearing = new_domain is None and new_id is None
        if not clearing and (not new_domain or new_id is None):
            raise AppError(
                "קישור מקור למשימה חייב לכלול סוג מקור ומזהה מקור",
                _INVALID_SOURCE,
            )
        if not clearing:
            self._validate_source(new_domain, new_id)
            resolved = self._resolve_client_from_source(new_domain, new_id)
            if resolved is not None:
                # Source is authoritative: recompute client_record_id from new source
                updates["client_record_id"] = resolved
        # Clearing source: preserve existing client_record_id (task becomes manual client task)

        updates["source_domain"] = new_domain
        updates["source_id"] = new_id
        return updates

    def complete(self, task_id: int, completed_by_user_id: int | None) -> Task:
        task = self.get(task_id)
        if task.status == TaskStatus.CANCELED:
            raise ConflictError("לא ניתן להשלים משימה שבוטלה", _CONFLICT)
        if task.status == TaskStatus.DONE:
            raise ConflictError("משימה כבר הושלמה", _CONFLICT)
        with self.transaction():
            task.status = TaskStatus.DONE
            task.completed_at = utcnow()
            task.completed_by_user_id = completed_by_user_id
            task.updated_at = utcnow()
        return task

    def cancel(self, task_id: int, canceled_by_user_id: int | None = None) -> Task:
        task = self.get(task_id)
        if task.status == TaskStatus.DONE:
            raise ConflictError("לא ניתן לבטל משימה שהושלמה", _CONFLICT)
        if task.status == TaskStatus.CANCELED:
            raise ConflictError("משימה כבר בוטלה", _CONFLICT)
        with self.transaction():
            task.status = TaskStatus.CANCELED
            task.canceled_at = utcnow()
            task.canceled_by_user_id = canceled_by_user_id
            task.updated_at = utcnow()
        return task

    def delete(self, task_id: int) -> None:
        task = self.get(task_id)
        with self.transaction():
            task.deleted_at = utcnow()
            task.updated_at = utcnow()

    def get(self, task_id: int) -> Task:
        task = self.repo.get_by_id(task_id)
        if not task or task.deleted_at is not None:
            raise NotFoundError(f"משימה {task_id} לא נמצאה", _NOT_FOUND)
        return task

    def bulk_complete(
        self, task_ids: list[int], completed_by_user_id: int | None
    ) -> TaskBulkActionResponse:
        deduped = list(dict.fromkeys(task_ids))
        found_map = self.repo.get_by_ids(deduped)

        results: list[tuple[bool, int, TaskBulkFailure | None]] = []
        to_complete: list[Task] = []

        for task_id in deduped:
            task = found_map.get(task_id)
            if task is None:
                results.append(
                    (
                        False,
                        task_id,
                        TaskBulkFailure(task_id=task_id, code=_NOT_FOUND, message="משימה לא נמצאה"),
                    )
                )
            elif task.status == TaskStatus.DONE:
                results.append((True, task_id, None))
            elif task.status == TaskStatus.CANCELED:
                results.append(
                    (
                        False,
                        task_id,
                        TaskBulkFailure(
                            task_id=task_id, code=_CONFLICT, message="לא ניתן להשלים משימה שבוטלה"
                        ),
                    )
                )
            else:
                results.append((True, task_id, None))
                to_complete.append(task)

        if to_complete:
            now = utcnow()
            with self.transaction():
                for task in to_complete:
                    task.status = TaskStatus.DONE
                    task.completed_at = now
                    task.completed_by_user_id = completed_by_user_id
                    task.updated_at = now

        succeeded = [task_id for is_ok, task_id, _ in results if is_ok]
        failed = [f for is_ok, _, f in results if not is_ok and f is not None]
        return TaskBulkActionResponse(succeeded=succeeded, failed=failed)

    def bulk_assign(
        self, task_ids: list[int], assignee_user_id: int | None
    ) -> TaskBulkActionResponse:
        if assignee_user_id is not None:
            from app.users.repositories.user_repository import UserRepository

            user = UserRepository(self.db).get_by_id(assignee_user_id)
            if user is None or not user.is_active:
                raise NotFoundError("המשתמש המשויך לא נמצא או אינו פעיל", _INVALID_ASSIGNEE)

        deduped = list(dict.fromkeys(task_ids))
        found_map = self.repo.get_by_ids(deduped)

        results: list[tuple[bool, int, TaskBulkFailure | None]] = []
        to_update: list[Task] = []

        for task_id in deduped:
            task = found_map.get(task_id)
            if task is None:
                results.append(
                    (
                        False,
                        task_id,
                        TaskBulkFailure(task_id=task_id, code=_NOT_FOUND, message="משימה לא נמצאה"),
                    )
                )
            elif task.status in _TERMINAL:
                results.append(
                    (
                        False,
                        task_id,
                        TaskBulkFailure(
                            task_id=task_id,
                            code=_CONFLICT,
                            message="לא ניתן לשנות שיוך למשימה שהושלמה או בוטלה",
                        ),
                    )
                )
            elif task.assigned_to_user_id == assignee_user_id:
                results.append((True, task_id, None))
            else:
                results.append((True, task_id, None))
                to_update.append(task)

        if to_update:
            now = utcnow()
            with self.transaction():
                for task in to_update:
                    task.assigned_to_user_id = assignee_user_id
                    task.updated_at = now

        succeeded = [task_id for is_ok, task_id, _ in results if is_ok]
        failed = [f for is_ok, _, f in results if not is_ok and f is not None]
        return TaskBulkActionResponse(succeeded=succeeded, failed=failed)

    def _validate_source(self, source_domain: str | None, source_id: int | None) -> None:
        if source_domain is None and source_id is None:
            return
        if not source_domain or source_id is None:
            raise AppError(
                "קישור מקור למשימה חייב לכלול סוג מקור ומזהה מקור",
                _INVALID_SOURCE,
            )
        source_type = normalize_source_domain(source_domain)
        if source_type is None:
            raise AppError("סוג המקור של המשימה אינו נתמך", _INVALID_SOURCE)
        if not source_exists(self.db, source_type, source_id):
            raise NotFoundError("הפריט המקושר למשימה לא נמצא", _NOT_FOUND)

    def _resolve_client_from_source(
        self, source_domain: str | None, source_id: int | None
    ) -> int | None:
        if source_domain is None or source_id is None:
            return None
        source_type = normalize_source_domain(source_domain)
        if source_type is None:
            return None
        Model = _SOURCE_CLIENT_MAP.get(source_type)  # type: ignore[arg-type]
        if Model is None:
            return None
        return self.db.scalar(
            select(Model.client_record_id).where(  # type: ignore[attr-defined]
                Model.id == source_id,
                Model.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        )

    def _validate_client_exists(self, client_record_id: int) -> None:
        from app.clients.services.client_service import get_client_or_raise

        get_client_or_raise(self.db, client_record_id)
