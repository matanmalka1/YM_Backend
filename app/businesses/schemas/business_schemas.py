from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.businesses.models.business import BusinessStatus
from app.core.api_types import ApiDateTime, PaginatedResponse
from app.core.schemas.validation import NonEmptyUpdateMixin

# ─── Requests ────────────────────────────────────────────────────────────────


class BusinessCreateRequest(BaseModel):
    """
    יצירת עסק חדש תחת לקוח קיים.
    client_record_id מועבר ב-URL: POST /clients/{client_record_id}/businesses
    """

    opened_at: date | None = None
    business_name: str = Field(..., max_length=100)
    notes: str | None = None

    @field_validator("business_name")
    @classmethod
    def normalize_business_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("יש להזין שם עסק")
        return value


class ClientBusinessCreateRequest(BaseModel):
    """
    פרטי עסק במסגרת פתיחת לקוח חדש.
    שם העסק נדרש לפתיחת פעילות ראשונה.
    """

    opened_at: date | None = None
    business_name: str = Field(..., max_length=100)
    notes: str | None = None

    @field_validator("business_name")
    @classmethod
    def normalize_business_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("יש להזין שם עסק")
        return value


class BusinessUpdateRequest(NonEmptyUpdateMixin):
    """עדכון פרטי עסק."""

    business_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = None
    status: BusinessStatus | None = None  # enum, non-nullable column
    closed_at: date | None = None

    @model_validator(mode="after")
    def _reject_null_for_required(self) -> BusinessUpdateRequest:
        for field in ("business_name", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"השדה {field} לא יכול להיות null")
        return self


# ─── Responses ────────────────────────────────────────────────────────────────


class BusinessResponse(BaseModel):
    """תגובת עסק."""

    id: int
    client_id: int | None = None
    business_name: str | None = None
    status: BusinessStatus
    opened_at: date
    closed_at: date | None = None
    notes: str | None = None
    created_at: ApiDateTime | None = None
    updated_at: ApiDateTime | None = None

    model_config = {"from_attributes": True}


class BusinessWithClientResponse(BusinessResponse):
    """תגובת עסק עם פרטי לקוח — לרשימת עסקים כללית."""

    client_full_name: str
    client_id_number: str

    model_config = {"from_attributes": True}


class BusinessListResponse(PaginatedResponse[BusinessWithClientResponse]):
    pass


class ClientBusinessesResponse(BaseModel):
    """רשימת עסקים של לקוח ספציפי."""

    client_id: int
    items: list[BusinessResponse]
    page: int
    page_size: int
    total: int
