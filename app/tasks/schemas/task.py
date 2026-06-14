from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.core.api_types import ApiDateTime, PaginatedResponse
from app.core.schemas.validation import NonEmptyUpdateMixin
from app.tasks.models.task import TaskPriority, TaskStatus
from app.users.models.user import UserRole


def _validate_positive_ids(v: list[int]) -> list[int]:
    if any(i <= 0 for i in v):
        raise ValueError("מזהי משימות חייבים להיות מספרים חיוביים")
    return v


class TaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    due_date: date | None = None
    assigned_to_user_id: int | None = Field(None, gt=0)
    assigned_role: UserRole | None = None
    source_domain: str | None = Field(None, max_length=100)
    source_id: int | None = Field(None, gt=0)
    client_record_id: int | None = Field(None, gt=0)
    action_key: str | None = Field(None, max_length=100)
    action_payload: dict[str, Any] | None = None


class TaskUpdateRequest(NonEmptyUpdateMixin):
    title: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
        | None
    ) = None
    description: str | None = None
    priority: TaskPriority | None = None  # non-nullable column
    due_date: date | None = None
    assigned_to_user_id: int | None = Field(None, gt=0)
    assigned_role: UserRole | None = None
    source_domain: str | None = Field(None, max_length=100)
    source_id: int | None = Field(None, gt=0)
    action_key: str | None = Field(None, max_length=100)
    action_payload: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _reject_null_for_required(self) -> TaskUpdateRequest:
        for field in ("title", "priority"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"השדה {field} לא יכול להיות null")
        return self


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    status: TaskStatus
    priority: TaskPriority
    due_date: date | None = None
    assigned_to_user_id: int | None = None
    assigned_role: UserRole | None = None
    source_domain: str | None = None
    source_id: int | None = None
    client_record_id: int | None = None
    action_key: str | None = None
    action_payload: dict[str, Any] | None = None
    created_by_user_id: int | None = None
    completed_by_user_id: int | None = None
    completed_at: ApiDateTime | None = None
    canceled_by_user_id: int | None = None
    canceled_at: ApiDateTime | None = None
    created_at: ApiDateTime
    updated_at: ApiDateTime

    model_config = {"from_attributes": True}


class TaskListResponse(PaginatedResponse[TaskResponse]):
    pass


class TaskBulkCompleteRequest(BaseModel):
    task_ids: list[int] = Field(min_length=1, max_length=100)

    @field_validator("task_ids")
    @classmethod
    def _positive(cls, v: list[int]) -> list[int]:
        return _validate_positive_ids(v)


class TaskBulkAssignRequest(BaseModel):
    task_ids: list[int] = Field(min_length=1, max_length=100)
    assignee_user_id: int | None = None

    @field_validator("task_ids")
    @classmethod
    def _positive(cls, v: list[int]) -> list[int]:
        return _validate_positive_ids(v)

    @field_validator("assignee_user_id")
    @classmethod
    def _positive_assignee(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("מזהה משתמש חייב להיות מספר חיובי")
        return v


class TaskBulkFailure(BaseModel):
    task_id: int
    code: str
    message: str


class TaskBulkActionResponse(BaseModel):
    succeeded: list[int]
    failed: list[TaskBulkFailure]
