from datetime import datetime

from sqlalchemy.orm import Session

from app.users.models.user_audit_log import AuditAction, AuditStatus, UserAuditLog
from app.users.repositories.user_audit_log_repository import UserAuditLogRepository


class AuditLogService:
    """Audit log orchestration for authentication and user actions."""

    def __init__(self, db: Session):
        self.repo = UserAuditLogRepository(db)

    def log(
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
    ) -> None:
        """Intentional pass-through to keep an anti-corruption boundary.

        All audit writes funnel through this method so future validation,
        normalization, or enrichment can be added without touching callers.
        """
        self.repo.create(
            action=action,
            status=status,
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            email=email,
            reason=reason,
            metadata=metadata,
            actor_display_name=actor_display_name,
            target_display_name=target_display_name,
        )

    def list_logs(
        self,
        page: int = 1,
        page_size: int = 20,
        action: AuditAction | None = None,
        target_user_id: int | None = None,
        actor_user_id: int | None = None,
        email: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ):
        items = self.repo.list(
            page=page,
            page_size=page_size,
            action=action,
            target_user_id=target_user_id,
            actor_user_id=actor_user_id,
            email=email,
            created_after=created_after,
            created_before=created_before,
        )
        total = self.repo.count(
            action=action,
            target_user_id=target_user_id,
            actor_user_id=actor_user_id,
            email=email,
            created_after=created_after,
            created_before=created_before,
        )
        return [self._to_dict(item) for item in items], total

    @staticmethod
    def _to_dict(log: UserAuditLog) -> dict:
        """Map an audit log ORM row into a plain dict for schema consumption.

        ``metadata_json`` is a JSONB object (dict) — no ``json.loads`` needed.
        """
        return {
            "id": log.id,
            "action": log.action,
            "actor_user_id": log.actor_user_id,
            "actor_display_name": log.actor_display_name,
            "target_user_id": log.target_user_id,
            "target_display_name": log.target_display_name,
            "email": log.email,
            "status": log.status,
            "reason": log.reason,
            "metadata": log.metadata_json,
            "created_at": log.created_at,
        }
