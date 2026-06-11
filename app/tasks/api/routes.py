from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Response

from app.common.source_types import WorkQueueSourceType
from app.core.exceptions import not_found_response
from app.tasks.models.task import TaskPriority, TaskStatus
from app.tasks.schemas.task import (
    TaskCreateRequest,
    TaskListResponse,
    TaskResponse,
    TaskUpdateRequest,
)
from app.tasks.services.task_service import TaskService
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get("", response_model=TaskListResponse)
def list_tasks(
    db: DBSession,
    status: TaskStatus | None = Query(None),
    priority: TaskPriority | None = Query(None),
    assigned_to_user_id: int | None = Query(None),
    assigned_role: UserRole | None = Query(None),
    source_domain: WorkQueueSourceType | None = Query(None),
    source_id: int | None = Query(None),
    due_before: date | None = Query(None),
    due_after: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    svc = TaskService(db)
    items, total = svc.list(
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
    return TaskListResponse(items=items, page=page, page_size=page_size, total=total)


@router.post("", response_model=TaskResponse, status_code=201)
def create_task(
    db: DBSession,
    user: CurrentUser,
    data: TaskCreateRequest,
):
    return TaskService(db).create(data, created_by_user_id=user.id)


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    responses=not_found_response(description="המשימה המבוקשת לא נמצאה"),
)
def get_task(db: DBSession, task_id: int):
    return TaskService(db).get(task_id)


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    responses=not_found_response(description="המשימה המבוקשת לא נמצאה"),
)
def update_task(
    db: DBSession,
    task_id: int,
    data: TaskUpdateRequest,
):
    return TaskService(db).update(task_id, data)


@router.post(
    "/{task_id}/complete",
    response_model=TaskResponse,
    responses=not_found_response(description="המשימה המבוקשת לא נמצאה"),
)
def complete_task(db: DBSession, user: CurrentUser, task_id: int):
    return TaskService(db).complete(task_id, completed_by_user_id=user.id)


@router.post(
    "/{task_id}/cancel",
    response_model=TaskResponse,
    responses=not_found_response(description="המשימה המבוקשת לא נמצאה"),
)
def cancel_task(db: DBSession, user: CurrentUser, task_id: int):
    return TaskService(db).cancel(task_id, canceled_by_user_id=user.id)


@router.delete(
    "/{task_id}",
    status_code=204,
    responses=not_found_response(description="המשימה המבוקשת לא נמצאה"),
)
def delete_task(db: DBSession, _user: CurrentUser, task_id: int):
    TaskService(db).delete(task_id)
    return Response(status_code=204)
