"""Pydantic schemas for the generic entity audit trail."""

from pydantic import BaseModel

from app.core.api_types import ApiDateTime, PaginatedResponse


class EntityAuditLogResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    performed_by: int | None = None
    performed_by_name: str | None = None
    actor_type: str
    actor_display_name: str | None = None
    action: str
    old_value: dict | list | None = None
    new_value: dict | list | None = None
    metadata_json: dict | list | None = None
    note: str | None = None
    performed_at: ApiDateTime

    model_config = {"from_attributes": True}


class EntityAuditTrailResponse(PaginatedResponse[EntityAuditLogResponse]):
    # True when the audited entity is soft- or hard-deleted; history stays
    # readable (§3a). Envelope-level — not repeated on every item.
    entity_deleted: bool
