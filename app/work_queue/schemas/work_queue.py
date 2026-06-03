from __future__ import annotations

from datetime import date
from enum import Enum as PyEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.common.source_types import WorkQueueSourceType
from app.core.action_schemas import ActionDescriptor
from app.users.models.user import UserRole


class WorkQueueUrgency(str, PyEnum):
    OVERDUE = "overdue"
    APPROACHING = "approaching"
    IMPORTANT = "important"
    UPCOMING = "upcoming"


class WorkQueueLinkedFilter(str, PyEnum):
    LINKED = "linked"
    UNLINKED = "unlinked"


class WorkQueueScope(str, PyEnum):
    SYSTEM = "system"
    MANUAL = "manual"


class WorkQueueSourceSummary(BaseModel):
    source_type: str
    source_id: int
    label: str
    route: str | None = None


class LinkedTaskSummary(BaseModel):
    id: int
    title: str
    status: str
    due_date: date | None = None
    priority: str | None = None
    assigned_user_id: int | None = None
    assigned_role: UserRole | None = None


class WorkQueueWarning(BaseModel):
    key: str
    label: str
    severity: Literal["info", "warning", "danger"] = "warning"


class WorkQueueItem(BaseModel):
    id: str = Field(
        pattern=r"^\w+:\d+$",
        description=(
            "Stable composite queue key in the form '{source_type}:{source_id}', "
            "for example 'charge:123'."
        )
    )
    source_type: WorkQueueSourceType
    source_id: int
    title: str
    description: str | None = None
    type_label: str | None = None
    status_label: str | None = None
    due_date: date | None = None
    urgency: WorkQueueUrgency
    client_record_id: int | None = None
    client_name: str | None = None
    office_client_number: int | None = None
    business_id: int | None = None
    source_summary: WorkQueueSourceSummary | None = None
    linked_tasks: list[LinkedTaskSummary] = Field(default_factory=list)
    linked_tasks_count: int = 0
    warnings: list[WorkQueueWarning] = Field(default_factory=list)
    available_actions: list[ActionDescriptor] = Field(default_factory=list)
    metadata: dict | None = None


class WorkQueueSummary(BaseModel):
    total: int
    manual_tasks: int
    linked: int
    unlinked: int
    overdue: int
    approaching: int
    important: int
    upcoming: int
    by_source_type: dict[WorkQueueSourceType, int]
    by_task_status: dict[str, int]


class WorkQueueListResponse(BaseModel):
    items: list[WorkQueueItem]
    total: int
    summary: WorkQueueSummary
