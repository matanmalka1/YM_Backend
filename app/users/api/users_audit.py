from app.core.error_codes import ErrorCode
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.core.exceptions import AppError
from app.core.pagination import MAX_PAGE_SIZE
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole
from app.users.models.user_audit_log import AuditAction
from app.users.schemas.user_management import (
    UserAuditLogListResponse,
    UserAuditLogResponse,
)
from app.users.services.audit_log_service import AuditLogService

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)


@router.get("/audit-logs", response_model=UserAuditLogListResponse)
def list_audit_logs(
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    action: AuditAction | None = None,
    target_user_id: int | None = None,
    actor_user_id: int | None = None,
    email: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
):
    if created_after is not None and created_before is not None and created_after > created_before:
        raise AppError(
            "טווח תאריכים לא תקין: created_after חייב להיות לפני created_before",
            ErrorCode.USER_INVALID_DATE_RANGE,
        )
    service = AuditLogService(db)
    items, total = service.list_logs(
        page=page,
        page_size=page_size,
        action=action,
        target_user_id=target_user_id,
        actor_user_id=actor_user_id,
        email=email,
        created_after=created_after,
        created_before=created_before,
    )
    return UserAuditLogListResponse(
        items=[UserAuditLogResponse(**item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )
