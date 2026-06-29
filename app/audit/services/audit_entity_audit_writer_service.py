"""Write abstraction for generic business entity audit events."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.audit.audit_constants import (
    ACTION_CREATED,
    ACTION_DELETED,
    ACTION_RESTORED,
    ACTION_STATUS_CHANGED,
    ACTION_UPDATED,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.audit.repositories.audit_entity_audit_log_repository import EntityAuditLogRepository


class EntityAuditWriter:
    def __init__(self, db: Session):
        self._repo = EntityAuditLogRepository(db)

    def append(
        self,
        *,
        entity_type: str,
        entity_id: int,
        actor_id: int | None,
        action: str,
        old_value: Any = None,
        new_value: Any = None,
        note: str | None = None,
        actor_type: str = "user",
        actor_display_name: str | None = None,
        metadata_json: Any = None,
    ) -> EntityAuditLog | None:
        if actor_id is None:
            return None
        return self._repo.append(
            entity_type=entity_type,
            entity_id=entity_id,
            performed_by=actor_id,
            action=action,
            old_value=self._serialize_value(old_value),
            new_value=self._serialize_value(new_value),
            note=note,
            actor_type=actor_type,
            actor_display_name=actor_display_name,
            metadata_json=self._serialize_value(metadata_json),
        )

    def record_create(
        self,
        entity_type: str,
        entity_id: int,
        actor_id: int | None,
        new_value: Any = None,
        note: str | None = None,
        *,
        actor_display_name: str | None = None,
    ) -> EntityAuditLog | None:
        return self.append(
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            action=ACTION_CREATED,
            new_value=new_value,
            note=note,
            actor_display_name=actor_display_name,
        )

    def record_update(
        self,
        entity_type: str,
        entity_id: int,
        actor_id: int | None,
        old_value: Any = None,
        new_value: Any = None,
        note: str | None = None,
        *,
        actor_display_name: str | None = None,
    ) -> EntityAuditLog | None:
        return self.append(
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            action=ACTION_UPDATED,
            old_value=old_value,
            new_value=new_value,
            note=note,
            actor_display_name=actor_display_name,
        )

    def record_delete(
        self,
        entity_type: str,
        entity_id: int,
        actor_id: int | None,
        old_value: Any = None,
        note: str | None = None,
        *,
        actor_display_name: str | None = None,
    ) -> EntityAuditLog | None:
        return self.append(
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            action=ACTION_DELETED,
            old_value=old_value,
            note=note,
            actor_display_name=actor_display_name,
        )

    def record_restore(
        self,
        entity_type: str,
        entity_id: int,
        actor_id: int | None,
        new_value: Any = None,
        note: str | None = None,
        *,
        actor_display_name: str | None = None,
    ) -> EntityAuditLog | None:
        return self.append(
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            action=ACTION_RESTORED,
            new_value=new_value,
            note=note,
            actor_display_name=actor_display_name,
        )

    def record_status_change(
        self,
        entity_type: str,
        entity_id: int,
        actor_id: int | None,
        old_status: Any,
        new_status: Any,
        note: str | None = None,
        *,
        actor_display_name: str | None = None,
    ) -> EntityAuditLog | None:
        return self.append(
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            action=ACTION_STATUS_CHANGED,
            old_value={"status": self._status_value(old_status)},
            new_value={"status": self._status_value(new_status)},
            note=note,
            actor_display_name=actor_display_name,
        )

    def _serialize_value(self, value: Any) -> Any:
        """Normalize a value to a JSON-safe object for the JSONB column.

        Returns the dict/list/scalar directly (no ``json.dumps``); the column
        stores the object. Bare strings are wrapped as ``{"value": ...}`` to keep
        a uniform object shape, matching the historical serializer behavior.
        """
        if value is None:
            return None
        if isinstance(value, str):
            value = {"value": value}
        return self._normalize_value(value)

    def _normalize_value(self, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {key: self._normalize_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._normalize_value(item) for item in value]
        return value

    def _status_value(self, status: Any) -> Any:
        return status.value if hasattr(status, "value") else status
