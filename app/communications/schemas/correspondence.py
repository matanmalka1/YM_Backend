import math
from datetime import UTC, datetime

from pydantic import BaseModel, field_validator

from app.communications.models.correspondence import CorrespondenceType
from app.core.api_types import ApiDateTime


def _validate_occurred_at(v: datetime | None) -> datetime | None:
    if v is None:
        return v
    now = datetime.now(UTC)
    v_aware = v if v.tzinfo is not None else v.replace(tzinfo=UTC)
    if v_aware > now:
        raise ValueError("תאריך ההתכתבות לא יכול להיות בעתיד")
    return v


class CorrespondenceCreateRequest(BaseModel):
    business_id: int | None = None
    contact_id: int | None = None
    correspondence_type: CorrespondenceType
    subject: str
    notes: str | None = None
    occurred_at: ApiDateTime

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_not_future(cls, v: datetime) -> datetime:
        return _validate_occurred_at(v)


class CorrespondenceUpdateRequest(BaseModel):
    business_id: int | None = None
    contact_id: int | None = None
    correspondence_type: CorrespondenceType | None = None
    subject: str | None = None
    notes: str | None = None
    occurred_at: ApiDateTime | None = None

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_not_future(cls, v: datetime | None) -> datetime | None:
        return _validate_occurred_at(v)


class CorrespondenceResponse(BaseModel):
    id: int
    client_record_id: int  # always present — primary anchor
    business_id: int | None = None  # optional — present when scoped to a business
    contact_id: int | None = None
    correspondence_type: CorrespondenceType
    subject: str
    notes: str | None = None
    occurred_at: ApiDateTime
    created_by: int
    created_at: ApiDateTime

    model_config = {"from_attributes": True}


class CorrespondenceListResponse(BaseModel):
    items: list[CorrespondenceResponse]
    page: int
    page_size: int
    total: int
    total_pages: int

    @classmethod
    def build(
        cls,
        items: list[CorrespondenceResponse],
        page: int,
        page_size: int,
        total: int,
    ) -> "CorrespondenceListResponse":
        return cls(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            total_pages=math.ceil(total / page_size) if page_size else 0,
        )
