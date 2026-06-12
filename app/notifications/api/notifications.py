"""Notification center HTTP endpoints."""

import datetime
from enum import IntEnum
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.core.exceptions import AppError
from app.core.openapi_responses import (
    bad_request_response,
    error_responses,
    not_found_response,
)
from app.notifications.models.notification import (
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)
from app.notifications.schemas.notification_schemas import (
    NotificationListResponse,
    NotificationPreviewRequest,
    NotificationPreviewResponse,
    NotificationResponse,
    NotificationResult,
    NotificationSendRequest,
    NotificationSummaryResponse,
)
from app.notifications.services.notification_service import NotificationService
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole


class NotificationPageSize(IntEnum):
    small = 25
    large = 50


router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
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
    page_size: NotificationPageSize = Query(NotificationPageSize.small),
):
    svc = NotificationService(db)
    page_size_value = int(page_size)
    items, total = svc.list_paginated(
        page=page,
        page_size=page_size_value,
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
        page_size=page_size_value,
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
def get_notification(notification_id: int, db: DBSession):
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
    openapi_extra={
        "parameters": [
            {
                "name": "X-Idempotency-Key",
                "in": "header",
                "required": True,
                "schema": {
                    "type": "string",
                    "format": "uuid",
                    "title": "X-Idempotency-Key",
                },
            }
        ]
    },
)
def send_notification(
    body: NotificationSendRequest,
    db: DBSession,
    user: CurrentUser,
    request: Request,
):
    x_idempotency_key = request.headers.get("X-Idempotency-Key")
    idempotency_key = x_idempotency_key.strip() if x_idempotency_key else ""
    if not idempotency_key:
        raise AppError(
            "נדרש X-Idempotency-Key לשליחת הודעה",
            "NOTIFICATION.MISSING_IDEMPOTENCY_KEY",
            status_code=400,
        )
    try:
        UUID(idempotency_key)
    except ValueError as exc:
        raise AppError(
            "X-Idempotency-Key חייב להיות UUID תקין",
            "NOTIFICATION.INVALID_IDEMPOTENCY_KEY",
            status_code=400,
        ) from exc
    svc = NotificationService(db)
    return svc.send(body, triggered_by=user.id, idempotency_key=idempotency_key)
