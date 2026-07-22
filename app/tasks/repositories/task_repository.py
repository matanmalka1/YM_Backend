from __future__ import annotations

from datetime import date

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.common.repositories.base_repository import BaseRepository
from app.common.source_types import WorkQueueSourceType
from app.tasks.models.task import Task, TaskPriority, TaskStatus
from app.users.models.user import UserRole


def _apply_filters(
    stmt,
    *,
    client_record_id: int | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    assigned_to_user_id: int | None = None,
    assigned_role: UserRole | None = None,
    source_domain: WorkQueueSourceType | None = None,
    source_id: int | None = None,
    due_before: date | None = None,
    due_after: date | None = None,
    search: str | None = None,
):
    if client_record_id is not None:
        stmt = stmt.where(Task.client_record_id == client_record_id)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if priority is not None:
        stmt = stmt.where(Task.priority == priority)
    if assigned_to_user_id is not None:
        stmt = stmt.where(Task.assigned_to_user_id == assigned_to_user_id)
    if assigned_role is not None:
        stmt = stmt.where(Task.assigned_role == assigned_role)
    if source_domain is not None:
        stmt = stmt.where(Task.source_domain == source_domain)
    if source_id is not None:
        stmt = stmt.where(Task.source_id == source_id)
    if due_before is not None:
        stmt = stmt.where(Task.due_date <= due_before)
    if due_after is not None:
        stmt = stmt.where(Task.due_date >= due_after)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(or_(Task.title.ilike(pattern), Task.description.ilike(pattern)))
    return stmt


class TaskRepository(BaseRepository[Task]):
    model = Task

    def __init__(self, db: Session):
        super().__init__(db)

    def create(
        self,
        title: str,
        created_by_user_id: int | None = None,
        **kwargs,
    ) -> Task:
        task = Task(title=title, created_by_user_id=created_by_user_id, **kwargs)
        self.db.add(task)
        self.db.flush()
        return task

    def list_active(
        self,
        client_record_id: int | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assigned_to_user_id: int | None = None,
        assigned_role: UserRole | None = None,
        source_domain: WorkQueueSourceType | None = None,
        source_id: int | None = None,
        due_before: date | None = None,
        due_after: date | None = None,
        search: str | None = None,
        sort_by: str = "created_at",
        order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Task], int]:
        filter_kwargs = dict(
            client_record_id=client_record_id,
            status=status,
            priority=priority,
            assigned_to_user_id=assigned_to_user_id,
            assigned_role=assigned_role,
            source_domain=source_domain,
            source_id=source_id,
            due_before=due_before,
            due_after=due_after,
            search=search,
        )

        base = _apply_filters(
            select(Task).where(Task.deleted_at.is_(None)),
            **filter_kwargs,
        )

        count_stmt = _apply_filters(
            select(func.count(Task.id)).where(Task.deleted_at.is_(None)),
            **filter_kwargs,
        )
        total: int = self.db.scalar(count_stmt) or 0

        sort_columns = {
            "created_at": Task.created_at,
            "due_date": Task.due_date,
            "priority": case(
                (Task.priority == TaskPriority.URGENT, 4),
                (Task.priority == TaskPriority.HIGH, 3),
                (Task.priority == TaskPriority.NORMAL, 2),
                else_=1,
            ),
            "title": Task.title,
        }
        sort_column = sort_columns[sort_by]
        ordering = (sort_column.asc() if order == "asc" else sort_column.desc()).nulls_last()
        data_stmt = self.apply_pagination(base.order_by(ordering, Task.id.desc()), page, page_size)
        items = list(self.db.scalars(data_stmt).all())
        return items, total

    def summarize_active(
        self,
        *,
        client_record_id: int | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assigned_to_user_id: int | None = None,
        assigned_role: UserRole | None = None,
        source_domain: WorkQueueSourceType | None = None,
        source_id: int | None = None,
        due_before: date | None = None,
        due_after: date | None = None,
        search: str | None = None,
    ) -> dict[TaskStatus, int]:
        stmt = _apply_filters(
            select(Task.status, func.count(Task.id)).where(Task.deleted_at.is_(None)),
            client_record_id=client_record_id,
            status=status,
            priority=priority,
            assigned_to_user_id=assigned_to_user_id,
            assigned_role=assigned_role,
            source_domain=source_domain,
            source_id=source_id,
            due_before=due_before,
            due_after=due_after,
            search=search,
        ).group_by(Task.status)
        return {row.status: row[1] for row in self.db.execute(stmt).all()}

    def list_for_work_queue(self) -> list[Task]:
        stmt = select(Task).where(
            Task.deleted_at.is_(None),
            Task.status == TaskStatus.OPEN,
        )
        return list(self.db.scalars(stmt).all())

    def list_by_ids(self, task_ids: set[int]) -> list[Task]:
        if not task_ids:
            return []
        stmt = select(Task).where(Task.id.in_(task_ids), Task.deleted_at.is_(None))
        return list(self.db.scalars(stmt).all())
