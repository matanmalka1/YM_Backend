from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.repositories.append_only_repository import AppendOnlyRepository
from app.users.models.user_audit_log import AuditAction, AuditStatus, UserAuditLog


class UserAuditLogRepository(AppendOnlyRepository):
    """Append-only data access layer for user audit logs.

    Inherits :class:`AppendOnlyRepository` (NOT ``BaseRepository``): auth/admin
    audit rows are immutable — this repository exposes only ``create`` (append)
    + ``list``/``count`` and has no update/delete surface.
    """

    def __init__(self, db: Session):
        super().__init__(db)

    def create(
        self,
        action: AuditAction,
        status: AuditStatus,
        actor_user_id: int | None = None,
        target_user_id: int | None = None,
        email: str | None = None,
        reason: str | None = None,
        metadata: dict | None = None,
        actor_display_name: str | None = None,
        target_display_name: str | None = None,
    ) -> UserAuditLog:
        log = UserAuditLog(
            action=action,
            status=status,
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            email=email,
            reason=reason,
            actor_display_name=actor_display_name,
            target_display_name=target_display_name,
            metadata_json=metadata,
        )
        self.db.add(log)
        self.db.flush()
        return log

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        action: AuditAction | None = None,
        target_user_id: int | None = None,
        actor_user_id: int | None = None,
        email: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list[UserAuditLog]:
        stmt = self._build_query(
            action=action,
            target_user_id=target_user_id,
            actor_user_id=actor_user_id,
            email=email,
            created_after=created_after,
            created_before=created_before,
        ).order_by(UserAuditLog.created_at.desc())
        stmt = self.apply_pagination(stmt, page, page_size)
        return list(self.db.scalars(stmt).all())

    def count(
        self,
        action: AuditAction | None = None,
        target_user_id: int | None = None,
        actor_user_id: int | None = None,
        email: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> int:
        stmt = self._build_query(
            action=action,
            target_user_id=target_user_id,
            actor_user_id=actor_user_id,
            email=email,
            created_after=created_after,
            created_before=created_before,
            count_only=True,
        )
        return self.db.scalar(stmt)

    def _build_query(
        self,
        action: AuditAction | None,
        target_user_id: int | None,
        actor_user_id: int | None,
        email: str | None,
        created_after: datetime | None,
        created_before: datetime | None,
        count_only: bool = False,
    ):
        stmt = select(func.count(UserAuditLog.id)) if count_only else select(UserAuditLog)
        if action is not None:
            stmt = stmt.where(UserAuditLog.action == action)
        if target_user_id is not None:
            stmt = stmt.where(UserAuditLog.target_user_id == target_user_id)
        if actor_user_id is not None:
            stmt = stmt.where(UserAuditLog.actor_user_id == actor_user_id)
        if email is not None:
            stmt = stmt.where(UserAuditLog.email == email)
        if created_after is not None:
            stmt = stmt.where(UserAuditLog.created_at >= created_after)
        if created_before is not None:
            stmt = stmt.where(UserAuditLog.created_at <= created_before)
        return stmt
