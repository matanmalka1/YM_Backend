from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.binders.models.binder import BinderCapacityStatus, BinderLocationStatus
from app.binders.models.binder_intake_material import MaterialType
from app.core.api_types import ApiDateTime, PaginatedResponse
from app.core.schemas.validation import NonEmptyUpdateMixin
from app.notifications.schemas.notification_schemas import NotificationResult

# ── Intake request ────────────────────────────────────────────────────────────


class BinderIntakeMaterialRequest(BaseModel):
    """פריט חומר בודד בתוך אירוע קבלה."""

    material_type: MaterialType
    business_id: int | None = None  # None = כל עסקי הלקוח
    annual_report_id: int | None = None
    vat_report_id: int | None = None
    period_year: int
    period_month_start: int = Field(ge=1, le=12)
    period_month_end: int = Field(ge=1, le=12)
    description: str | None = None


class BinderReceiveRequest(BaseModel):
    """
    קבלת חומרים לקלסר.
    אם binder_number קיים ופעיל — מוסיף intake לקלסר קיים.
    אם לא — יוצר קלסר חדש.
    """

    client_record_id: int  # קלסר שייך ללקוח
    received_at: date  # תאריך קבלת החומרים (ב-intake)
    received_by: int
    open_new_binder: bool = False  # True = סמן קלסר קיים כמלא ופתח חדש
    notes: str | None = None
    materials: list[BinderIntakeMaterialRequest] = Field(..., min_length=1)


class BinderHandoverToClientRequest(BaseModel):
    handover_recipient_name: str | None = None
    handed_over_at: date | None = None


# ── Core response ─────────────────────────────────────────────────────────────


class BinderResponse(BaseModel):
    id: int
    client_record_id: int
    office_client_number: int | None = None
    client_name: str | None = None  # enriched by service
    client_id_number: str | None = None  # enriched by service
    binder_number: str
    period_start: date | None = None
    period_end: date | None = None
    location_status: BinderLocationStatus
    capacity_status: BinderCapacityStatus
    ready_for_handover_at: ApiDateTime | None = None
    handed_over_at: date | None = None
    handover_recipient_name: str | None = None
    notes: str | None = None
    created_at: ApiDateTime
    updated_at: ApiDateTime | None = None
    # ── Derived (computed by service, not stored) ─────────────────────────────
    days_in_office: int | None = None  # today - period_start
    available_actions: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class BinderListCounters(BaseModel):
    total: int
    location_in_office: int
    location_ready_for_handover: int
    location_handed_over: int
    capacity_open: int
    capacity_full: int


class BinderListResponse(PaginatedResponse[BinderResponse]):
    counters: BinderListCounters


# ── Intake responses ──────────────────────────────────────────────────────────


class BinderIntakeMaterialResponse(BaseModel):
    id: int
    intake_id: int
    material_type: MaterialType
    business_id: int | None = None
    annual_report_id: int | None = None
    vat_report_id: int | None = None
    period_year: int
    period_month_start: int
    period_month_end: int
    description: str | None = None
    created_at: ApiDateTime

    model_config = {"from_attributes": True}


class BinderIntakeResponse(BaseModel):
    id: int
    binder_id: int
    received_at: date
    received_by: int
    received_by_name: str | None = None  # enriched by service
    notes: str | None = None
    created_at: ApiDateTime
    materials: list[BinderIntakeMaterialResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class BinderIntakeListResponse(PaginatedResponse[BinderIntakeResponse]):
    pass


class BinderReceiveResult(BaseModel):
    """תוצאת קבלת חומרים — binder + intake."""

    binder: BinderResponse
    intake: BinderIntakeResponse
    is_new_binder: bool


class BinderIntakeUpdateRequest(NonEmptyUpdateMixin):
    """עריכת אירוע קבלה קיים."""

    received_at: date | None = None
    received_by: int | None = None
    notes: str | None = None
    client_record_id: int | None = None
    binder_id: int | None = None
    business_ids: list[int] | None = None
    annual_report_ids: list[int] | None = None
    vat_report_ids: list[int] | None = None

    @model_validator(mode="after")
    def _reject_null_for_required(self) -> BinderIntakeUpdateRequest:
        # These map to non-nullable columns / transfer targets, and the FK
        # association lists use [] to clear, never null. Explicit null is invalid.
        for field in (
            "received_at",
            "received_by",
            "binder_id",
            "client_record_id",
            "business_ids",
            "annual_report_ids",
            "vat_report_ids",
        ):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"השדה {field} לא יכול להיות null")
        return self


class BinderMarkReadyForHandoverBulkRequest(BaseModel):
    client_record_id: int
    until_period_year: int
    until_period_month: int = Field(ge=1, le=12)


# ── Handover ─────────────────────────────────────────────────────────────────


class BinderReadyForHandoverResponse(BaseModel):
    binder: BinderResponse
    notification: NotificationResult


class BinderHandoverRequest(BaseModel):
    """בקשת מסירת קלסרים מרובים ללקוח בבת אחת."""

    client_record_id: int
    binder_ids: list[int] = Field(min_length=1)
    received_by_name: str
    handed_over_at: date
    until_period_year: int
    until_period_month: int = Field(ge=1, le=12)
    notes: str | None = None


class BinderHandoverResponse(BaseModel):
    id: int
    client_record_id: int
    received_by_name: str
    handed_over_at: date
    until_period_year: int
    until_period_month: int
    binder_ids: list[int]
    notes: str | None = None
    created_at: ApiDateTime

    model_config = {"from_attributes": True}
