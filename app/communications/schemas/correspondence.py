from datetime import UTC, datetime

from pydantic import BaseModel, field_validator, model_validator

from app.communications.models.correspondence import CorrespondenceType
from app.core.api_types import ApiDateTime, NonBlankStr
from app.core.schemas.validation import NonEmptyUpdateMixin


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


class CorrespondenceUpdateRequest(NonEmptyUpdateMixin):
    business_id: int | None = None
    contact_id: int | None = None
    correspondence_type: CorrespondenceType | None = None
    subject: NonBlankStr | None = None
    notes: str | None = None
    occurred_at: ApiDateTime | None = None

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_not_future(cls, v: datetime | None) -> datetime | None:
        return _validate_occurred_at(v)

    @model_validator(mode="after")
    def _reject_null_for_required(self) -> CorrespondenceUpdateRequest:
        for field in ("correspondence_type", "subject", "occurred_at"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"השדה {field} לא יכול להיות null")
        return self


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
    updated_at: ApiDateTime | None = None

    model_config = {"from_attributes": True}


class CorrespondenceListResponse(BaseModel):
    # #42: total_pages removed — it's derived (ceil(total/page_size)) and computed
    # client-side; envelope matches the standard PaginatedResponse shape.
    items: list[CorrespondenceResponse]
    page: int
    page_size: int
    total: int

    @classmethod
    def build(
        cls,
        items: list[CorrespondenceResponse],
        page: int,
        page_size: int,
        total: int,
    ) -> CorrespondenceListResponse:
        return cls(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
        )
