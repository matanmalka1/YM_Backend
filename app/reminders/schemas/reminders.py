from typing import Any

from pydantic import BaseModel, Field

from app.core.api_types import ApiDateTime, PaginatedResponse
from app.reminders.models.reminder import ReminderActionType, ReminderStatus


class ReminderCreateRequest(BaseModel):
    fire_at: ApiDateTime
    action_type: ReminderActionType
    source_domain: str | None = Field(None, max_length=100)
    source_id: int | None = Field(None, gt=0)
    target_task_id: int | None = Field(None, gt=0)
    notification_template_key: str | None = Field(None, max_length=100)
    payload: dict[str, Any] | None = None


class ReminderResponse(BaseModel):
    id: int
    fire_at: ApiDateTime
    status: ReminderStatus
    action_type: ReminderActionType
    source_domain: str | None = None
    source_id: int | None = None
    target_task_id: int | None = None
    notification_template_key: str | None = None
    payload: dict[str, Any] | None = None
    client_record_id: int | None = None
    client_name: str | None = None
    office_client_number: int | None = None
    created_by_user_id: int | None = None
    fired_at: ApiDateTime | None = None
    failure_reason: str | None = None
    created_at: ApiDateTime
    updated_at: ApiDateTime

    model_config = {"from_attributes": True}


class FireDueResponse(BaseModel):
    processed: int
    fired: int
    failed: int


class ReminderListResponse(PaginatedResponse[ReminderResponse]):
    pass
