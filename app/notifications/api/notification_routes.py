"""Notification center HTTP endpoints."""

import datetime

from fastapi import APIRouter, Depends, Query

from app.core.error_codes import ErrorCode
from app.core.openapi_responses import (
    bad_request_response,
    error_responses,
    not_found_response,
)
from app.core.pagination import MAX_PAGE_SIZE
from app.core.path_params import PathId
from app.infrastructure.idempotency.dependency import (
    OptionalIdempotencyKeyHeader,
    normalize_idempotency_key_header,
)
from app.notifications.models.notification import (
    CLIENT_LEVEL_MANUAL_NOTIFICATION_TRIGGERS,
    TRIGGER_DOMAIN,
    TRIGGER_LABELS,
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)
from app.notifications.schemas.notification_schemas import (
    NotificationListResponse,
    NotificationMetadataResponse,
    NotificationPreviewRequest,
    NotificationPreviewResponse,
    NotificationResponse,
    NotificationResult,
    NotificationSendRequest,
    NotificationSummaryResponse,
)
from app.notifications.services.notification_service import NotificationService
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get("/metadata", response_model=NotificationMetadataResponse)
def get_notification_metadata():
    return NotificationMetadataResponse(
        triggers=[
            {
                "value": trigger,
                "label": TRIGGER_LABELS[trigger],
                "domain_label": TRIGGER_DOMAIN[trigger],
                "client_level_manual": trigger in CLIENT_LEVEL_MANUAL_NOTIFICATION_TRIGGERS,
            }
            for trigger in NotificationTrigger
        ]
    )


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    db: DBSession,
    client_record_id: int | None = None,
    business_id: int | None = None,
    status: NotificationStatus | None = None,
    trigger: NotificationTrigger | None = None,
    channel: NotificationChannel | None = None,
    triggered_by: int | None = None,
    created_after: datetime.datetime | None = None,
    created_before: datetime.datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    svc = NotificationService(db)
    items, total = svc.list_paginated(
        page=page,
        page_size=page_size,
        client_record_id=client_record_id,
        business_id=business_id,
        status=status,
        trigger=trigger,
        channel=channel,
        triggered_by=triggered_by,
        created_after=created_after,
        created_before=created_before,
    )
    return NotificationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/summary", response_model=NotificationSummaryResponse)
def get_notification_summary(
    db: DBSession,
    client_record_id: int | None = None,
    business_id: int | None = None,
):
    svc = NotificationService(db)
    return svc.get_summary(client_record_id=client_record_id, business_id=business_id)


@router.get(
    "/{notification_id}",
    response_model=NotificationResponse,
    responses=not_found_response(description="ההודעה המבוקשת לא נמצאה"),
)
def get_notification(notification_id: PathId, db: DBSession):
    return NotificationService(db).get_detail(notification_id)


@router.post(
    "/preview",
    response_model=NotificationPreviewResponse,
    responses=error_responses(bad_request_response(description="נתוני ההודעה אינם תקינים")),
)
def preview_notification(
    body: NotificationPreviewRequest,
    db: DBSession,
    user: CurrentUser,
):
    svc = NotificationService(db)
    return svc.preview(body, triggered_by=user.id)


@router.post(
    "/send",
    response_model=NotificationResult,
    responses=error_responses(
        bad_request_response(description="נדרש מפתח אידמפוטנטיות תקין לשליחת ההודעה")
    ),
)
def send_notification(
    body: NotificationSendRequest,
    db: DBSession,
    user: CurrentUser,
    x_idempotency_key: OptionalIdempotencyKeyHeader = None,
):
    idempotency_key = normalize_idempotency_key_header(
        x_idempotency_key,
        missing_message="נדרש X-Idempotency-Key לשליחת הודעה",
        missing_code=ErrorCode.NOTIFICATION_MISSING_IDEMPOTENCY_KEY,
        invalid_message="X-Idempotency-Key חייב להיות באורך 8 עד 128 תווים",
        invalid_code=ErrorCode.NOTIFICATION_INVALID_IDEMPOTENCY_KEY,
    )
    svc = NotificationService(db)
    return svc.send(
        body,
        triggered_by=user.id,
        idempotency_key=idempotency_key,
        actor_name=user.full_name,
    )
