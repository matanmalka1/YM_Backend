"""Repository for EntityAuditLog entities."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.models.entity_audit_log import EntityAuditLog
from app.common.repositories.base_repository import BaseRepository


class EntityAuditLogRepository(BaseRepository[EntityAuditLog]):
    def __init__(self, db: Session):
        self.db = db

    def append(
        self,
        entity_type: str,
        entity_id: int,
        performed_by: int,
        action: str,
        old_value: str | None = None,
        new_value: str | None = None,
        note: str | None = None,
    ) -> EntityAuditLog:
        entry = EntityAuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            performed_by=performed_by,
            action=action,
            old_value=old_value,
            new_value=new_value,
            note=note,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    @staticmethod
    def _audit_trail_filters(
        entity_type: str,
        entity_id: int,
        *,
        action: str | None = None,
        user_id: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list:
        """Filter set shared by ``get_audit_trail`` and ``count_audit_trail``.

        ``(entity_type, entity_id)`` scope always applies; optional filters narrow
        further. ``user_id`` maps to ``performed_by`` and ``created_*`` to
        ``performed_at`` (the audit timestamp).
        """
        filters = [
            EntityAuditLog.entity_type == entity_type,
            EntityAuditLog.entity_id == entity_id,
        ]
        if action:
            filters.append(EntityAuditLog.action == action)
        if user_id is not None:
            filters.append(EntityAuditLog.performed_by == user_id)
        if created_after is not None:
            filters.append(EntityAuditLog.performed_at >= created_after)
        if created_before is not None:
            filters.append(EntityAuditLog.performed_at <= created_before)
        return filters

    def get_audit_trail(
        self,
        entity_type: str,
        entity_id: int,
        limit: int = 50,
        offset: int = 0,
        *,
        action: str | None = None,
        user_id: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list[EntityAuditLog]:
        filters = self._audit_trail_filters(
            entity_type,
            entity_id,
            action=action,
            user_id=user_id,
            created_after=created_after,
            created_before=created_before,
        )
        return self.db.scalars(
            select(EntityAuditLog)
            .where(*filters)
            .order_by(EntityAuditLog.performed_at.desc(), EntityAuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()

    def count_audit_trail(
        self,
        entity_type: str,
        entity_id: int,
        *,
        action: str | None = None,
        user_id: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> int:
        filters = self._audit_trail_filters(
            entity_type,
            entity_id,
            action=action,
            user_id=user_id,
            created_after=created_after,
            created_before=created_before,
        )
        return self.db.scalar(select(func.count(EntityAuditLog.id)).where(*filters))

    def list_recent(self, limit: int = 5) -> list[EntityAuditLog]:
        return self.db.scalars(
            select(EntityAuditLog)
            .order_by(EntityAuditLog.performed_at.desc(), EntityAuditLog.id.desc())
            .limit(limit)
        ).all()
