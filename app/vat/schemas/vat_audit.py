"""Pydantic schemas for VAT audit trail."""

from pydantic import BaseModel

from app.core.api_types import ApiDateTime


class VatAuditLogResponse(BaseModel):
    id: int
    work_item_id: int
    performed_by: int
    performed_by_name: str | None = None
    action: str
    old_value: str | None = None
    new_value: str | None = None
    note: str | None = None
    performed_at: ApiDateTime

    model_config = {"from_attributes": True}


class VatAuditTrailResponse(BaseModel):
    items: list[VatAuditLogResponse]
    total: int
    page: int
    page_size: int
