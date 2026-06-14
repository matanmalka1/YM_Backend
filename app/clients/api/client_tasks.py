from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.common.source_types import WorkQueueSourceType
from app.core.openapi_responses import error_responses, not_found_response
from app.core.pagination import MAX_PAGE_SIZE
from app.core.path_params import PathId
from app.tasks.models.task import TaskStatus
from app.tasks.schemas.task import TaskListResponse
from app.tasks.services.task_service import TaskService
from app.users.api.deps import DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/clients",
    tags=["clients"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get(
    "/{client_record_id}/tasks",
    response_model=TaskListResponse,
    responses=error_responses(not_found_response(description="הלקוח לא נמצא")),
)
def list_client_tasks(
    db: DBSession,
    client_record_id: PathId,
    status: TaskStatus | None = Query(None),
    assigned_to_user_id: int | None = Query(None),
    source_domain: WorkQueueSourceType | None = Query(None),
    due_before: date | None = Query(None),
    due_after: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    svc = TaskService(db)
    items, total = svc.list_by_client(
        client_record_id=client_record_id,
        status=status,
        assigned_to_user_id=assigned_to_user_id,
        source_domain=source_domain,
        due_before=due_before,
        due_after=due_after,
        page=page,
        page_size=page_size,
    )
    return TaskListResponse(items=items, page=page, page_size=page_size, total=total)
