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
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
):
    if from_ts is not None and to_ts is not None and from_ts > to_ts:
        raise AppError("טווח תאריכים לא תקין: from חייב להיות לפני to", "USER.INVALID_DATE_RANGE")
    service = AuditLogService(db)
    items, total = service.list_logs(
        page=page,
        page_size=page_size,
        action=action,
        target_user_id=target_user_id,
        actor_user_id=actor_user_id,
        email=email,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    return UserAuditLogListResponse(
        items=[UserAuditLogResponse(**item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )
