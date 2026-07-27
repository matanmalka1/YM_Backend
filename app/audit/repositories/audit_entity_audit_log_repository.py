"""Append-only repository for EntityAuditLog rows.

Inherits :class:`AppendOnlyRepository` (NOT ``BaseRepository``): audit rows are
immutable, so this repository exposes only ``append`` + read queries and has no
``update``/``delete``/``soft_delete``/``hard_delete`` surface.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.common.repositories.append_only_repository import AppendOnlyRepository


class EntityAuditLogRepository(AppendOnlyRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def append(
        self,
        entity_type: str,
        entity_id: int,
        performed_by: int | None,
        action: str,
        old_value: Any = None,
        new_value: Any = None,
        note: str | None = None,
        *,
        actor_type: str = "user",
        actor_display_name: str | None = None,
        metadata_json: Any = None,
    ) -> EntityAuditLog:
        entry = EntityAuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            performed_by=performed_by,
            actor_type=actor_type,
            actor_display_name=actor_display_name,
            action=action,
            old_value=old_value,
            new_value=new_value,
            metadata_json=metadata_json,
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
        page: int = 1,
        page_size: int = 50,
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
        stmt = self.apply_pagination(
            select(EntityAuditLog)
            .where(*filters)
            .order_by(EntityAuditLog.performed_at.desc(), EntityAuditLog.id.desc()),
            page,
            page_size,
        )
        return self.db.scalars(stmt).all()

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

    def list_by_entity(self, entity_type: str, entity_id: int) -> list[EntityAuditLog]:
        """Every audit row for a single entity, newest first — unpaginated."""
        return list(
            self.db.scalars(
                select(EntityAuditLog)
                .where(
                    EntityAuditLog.entity_type == entity_type,
                    EntityAuditLog.entity_id == entity_id,
                )
                .order_by(EntityAuditLog.performed_at.desc(), EntityAuditLog.id.desc())
            ).all()
        )

    def list_by_entities(self, entity_type: str, entity_ids: list[int]) -> list[EntityAuditLog]:
        """Every audit row for a set of entities of one type, newest first."""
        return self.list_all_by_entities(entity_type, entity_ids)

    def list_all_by_entities(self, entity_type: str, entity_ids: list[int]) -> list[EntityAuditLog]:
        """Every audit row for a set of entities, newest first — unpaginated.

        Used by the timeline aggregator, which paginates the merged event list itself.
        """
        if not entity_ids:
            return []
        return self.db.scalars(
            select(EntityAuditLog)
            .where(
                EntityAuditLog.entity_type == entity_type,
                EntityAuditLog.entity_id.in_(entity_ids),
            )
            .order_by(EntityAuditLog.performed_at.desc(), EntityAuditLog.id.desc())
        ).all()

    def list_for_client_context(
        self,
        client_record_id: int,
        *,
        entity_types: list[str] | None = None,
        business_ids: list[int] | None = None,
        limit: int | None = None,
    ) -> list[EntityAuditLog]:
        """Audit rows whose ``metadata_json.client_record_id`` matches a client.

        Uses the §8b PostgreSQL expression index
        ``idx_entity_audit_client_ctx`` on ``((metadata_json->>'client_record_id'),
        performed_at)``. ``entity_types``/``business_ids`` narrow further.
        """
        stmt = select(EntityAuditLog).where(
            EntityAuditLog.metadata_json["client_record_id"].as_string() == str(client_record_id)
        )
        if entity_types:
            stmt = stmt.where(EntityAuditLog.entity_type.in_(entity_types))
        if business_ids:
            stmt = stmt.where(
                EntityAuditLog.metadata_json["business_id"]
                .as_string()
                .in_([str(bid) for bid in business_ids])
            )
        stmt = stmt.order_by(EntityAuditLog.performed_at.desc(), EntityAuditLog.id.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def list_recent(self, limit: int = 5) -> list[EntityAuditLog]:
        return self.db.scalars(
            select(EntityAuditLog)
            .order_by(EntityAuditLog.performed_at.desc(), EntityAuditLog.id.desc())
            .limit(limit)
        ).all()

    def list_recent_activity(self, limit: int = 5) -> list[EntityAuditLog]:
        """Most-recent audit rows across all entity types (dashboard feed)."""
        return self.list_recent(limit)
