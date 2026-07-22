from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.api_types import ApiDateTime, PaginatedResponse
from app.notifications.models.notification import (
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)

# ── Request schemas ───────────────────────────────────────────────────────────


class NotificationPreviewRequest(BaseModel):
    client_record_id: int = Field(gt=0)
    trigger: NotificationTrigger
    entity_id: int | None = Field(None, gt=0)
    business_id: int | None = Field(None, gt=0)
    confirm_recent_duplicate: bool = False


class NotificationSendOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str | None = None
    body: str | None = None


class NotificationSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_record_id: int = Field(gt=0)
    trigger: NotificationTrigger
    entity_id: int | None = Field(None, gt=0)
    business_id: int | None = Field(None, gt=0)
    channel: Literal["email"] | None = (
        None  # whatsapp defined in NotificationChannel but delivery not yet implemented
    )
    overrides: NotificationSendOverrides | None = None
    confirm_recent_duplicate: bool = False


# ── Result schemas ────────────────────────────────────────────────────────────


class NotificationResult(BaseModel):
    status: Literal["sent", "failed", "skipped", "blocked"]
    notification_id: int | None = None
    reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class NotificationPreviewResponse(BaseModel):
    can_send: bool
    status: Literal["ready", "blocked"]
    reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    recipient: str | None = None
    subject: str | None = None
    body: str | None = None


# ── Read schemas ──────────────────────────────────────────────────────────────


class NotificationResponse(BaseModel):
    id: int
    client_record_id: int
    client_name: str | None = None
    business_id: int | None = None
    business_name: str | None = None
    binder_id: int | None = None
    annual_report_id: int | None = None
    signature_request_id: int | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    trigger: NotificationTrigger
    trigger_label: str = ""
    domain_label: str = ""
    channel: NotificationChannel
    recipient: str | None = None
    content_snapshot: str
    subject_snapshot: str | None = None
    status: NotificationStatus
    sent_at: ApiDateTime | None = None
    failed_at: ApiDateTime | None = None
    error_message: str | None = None
    retry_count: int
    triggered_by: int | None = None
    created_at: ApiDateTime

    model_config = {"from_attributes": True}


class NotificationListItem(BaseModel):
    """Thin DTO for notification list/table rows.

    Contains the fields rendered by notification list rows across the
    notifications table, the bell drawer, and the per-client tab — including
    client identity fields for the global table and the ``content_snapshot``
    preview and ``business_name`` shown inline in the compact lists. Routing references and delivery/debug fields
    (entity_*, channel, sent_at/failed_at, error_message, retry_count,
    triggered_by) stay on ``NotificationResponse`` and are served by
    ``GET /notifications/{notification_id}``.
    """

    id: int
    client_record_id: int
    client_name: str | None = None
    client_id_number: str | None = None
    office_client_number: int | None = None
    business_name: str | None = None
    trigger: NotificationTrigger
    trigger_label: str = ""
    domain_label: str = ""
    status: NotificationStatus
    recipient: str | None = None
    content_snapshot: str
    subject_snapshot: str | None = None
    created_at: ApiDateTime

    model_config = {"from_attributes": True}


class NotificationSummaryResponse(BaseModel):
    pending: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    total: int = 0


class NotificationTriggerOption(BaseModel):
    value: NotificationTrigger
    label: str
    domain_label: str
    client_level_manual: bool


class NotificationMetadataResponse(BaseModel):
    triggers: list[NotificationTriggerOption]


class NotificationListResponse(PaginatedResponse[NotificationListItem]):
    pass


# ── Bulk result ───────────────────────────────────────────────────────────────


class BulkNotificationResultItem(BaseModel):
    entity_id: int | None = None
    client_record_id: int | None = None
    status: Literal["sent", "failed", "skipped", "blocked"]
    notification_id: int | None = None
    reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class BulkNotificationResult(BaseModel):
    total: int
    sent: int
    failed: int
    skipped: int
    blocked: int
    results: list[BulkNotificationResultItem] = Field(default_factory=list)
