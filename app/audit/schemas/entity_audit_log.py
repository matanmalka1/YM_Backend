"""Pydantic schemas for the generic entity audit trail."""

from pydantic import BaseModel

from app.core.api_types import ApiDateTime


class EntityAuditLogResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    performed_by: int
    performed_by_name: str | None = None
    action: str
    old_value: str | None = None
    new_value: str | None = None
    note: str | None = None
    performed_at: ApiDateTime

    model_config = {"from_attributes": True}


class EntityAuditTrailResponse(BaseModel):
    items: list[EntityAuditLogResponse]
    total: int
    page: int
    page_size: int
