from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.tasks.models.task import TaskStatus
from app.users.api.deps import DBSession, require_role
from app.users.models.user import UserRole
from app.work_queue.schemas.work_queue import (
    WorkQueueLinkedFilter,
    WorkQueueListResponse,
    WorkQueueScope,
    WorkQueueSourceType,
    WorkQueueUrgency,
)
from app.work_queue.services.work_queue_service import WorkQueueService

router = APIRouter(prefix="/work-queue", tags=["work-queue"])


class WorkQueueFilterParams:
    def __init__(
        self,
        client_record_id: int | None = Query(None),
        business_id: int | None = Query(None),
        exclude_source_types: list[WorkQueueSourceType] | None = Query(None),
        include_task_history: bool = Query(False),
        search: str | None = Query(None),
        source_type: WorkQueueSourceType | None = Query(None),
        urgency: WorkQueueUrgency | None = Query(None),
        task_status: TaskStatus | None = Query(None),
        linked: WorkQueueLinkedFilter | None = Query(None),
        scope: WorkQueueScope | None = Query(None),
    ):
        self.client_record_id = client_record_id
        self.business_id = business_id
        self.exclude_source_types = exclude_source_types
        self.include_task_history = include_task_history
        self.search = search
        self.source_type = source_type
        self.urgency = urgency
        self.task_status = task_status
        self.linked = linked
        self.scope = scope


@router.get(
    "",
    response_model=WorkQueueListResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def list_work_queue(
    db: DBSession,
    filters: WorkQueueFilterParams = Depends(),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    return WorkQueueService(db).list_items_with_total(
        client_record_id=filters.client_record_id,
        business_id=filters.business_id,
        exclude_source_types=filters.exclude_source_types,
        include_task_history=filters.include_task_history,
        search=filters.search,
        source_type=filters.source_type,
        urgency=filters.urgency,
        task_status=filters.task_status,
        linked=filters.linked,
        scope=filters.scope,
        page=page,
        page_size=page_size,
    )
