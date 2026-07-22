"""Pydantic request / response schemas for the VAT Reports module."""

from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.common.enums import SubmissionMethod, VatType
from app.core.action_schemas import ActionDescriptor
from app.core.api_types import ApiDateTime, ApiDecimal, PaginatedResponse, PeriodStr
from app.core.schemas.validation import NonEmptyUpdateMixin
from app.vat.models.vat_enums import VatWorkItemStatus

# ── Work Item ─────────────────────────────────────────────────────────────────


class VatWorkItemCreateRequest(BaseModel):
    client_record_id: int
    period: PeriodStr
    assigned_to: int | None = None
    mark_pending: bool = False
    pending_materials_note: str | None = None


class VatWorkItemUpdateRequest(NonEmptyUpdateMixin):
    assigned_to: int | None = None
    pending_materials_note: str | None = None


class VatExpenseCategoryBreakdownResponse(BaseModel):
    category: str
    label: str
    deduction_rate: ApiDecimal
    net_amount: ApiDecimal
    gross_vat: ApiDecimal
    deductible_vat: ApiDecimal


class VatBreakdownResponse(BaseModel):
    income_net: ApiDecimal
    total_output_vat: ApiDecimal
    expenses: list[VatExpenseCategoryBreakdownResponse]
    total_expense_net: ApiDecimal
    total_gross_vat: ApiDecimal
    total_input_vat: ApiDecimal


class VatWorkItemResponse(BaseModel):
    id: int
    client_record_id: int
    office_client_number: int | None = None  # enriched by service
    client_name: str | None = None  # enriched by service
    client_id_number: str | None = None  # enriched by service
    client_status: str | None = None  # enriched by service
    period: str
    period_type: VatType  # snapshot at creation — immutable historical record
    status: VatWorkItemStatus
    pending_materials_note: str | None = None
    total_output_vat: ApiDecimal
    total_input_vat: ApiDecimal
    net_vat: ApiDecimal
    total_output_net: ApiDecimal  # קיים במודל — שדה 87
    total_input_net: ApiDecimal  # קיים במודל — שדה 66
    final_vat_amount: ApiDecimal | None = None
    is_overridden: bool
    override_justification: str | None = None
    submission_method: SubmissionMethod | None = None  # שם חדש במודל
    filed_at: ApiDateTime | None = None
    filed_by: int | None = None
    filed_by_name: str | None = None
    submission_reference: str | None = None
    is_amendment: bool = False
    amends_item_id: int | None = None
    created_by: int
    assigned_to: int | None = None
    assigned_to_name: str | None = None
    created_at: ApiDateTime
    updated_at: ApiDateTime
    # Derived — not stored
    submission_deadline: date | None = None
    statutory_deadline: date | None = None
    extended_deadline: date | None = None
    days_until_deadline: int | None = None
    is_overdue: bool | None = None
    available_actions: list[ActionDescriptor] = Field(default_factory=list)
    breakdown: VatBreakdownResponse

    model_config = {"from_attributes": True}


class VatWorkItemListItem(BaseModel):
    """Thin DTO for VAT work-item list/table rows.

    Contains only the fields rendered by the VAT list, grouped table, and
    grouped cards. Detail-only fields (raw totals, override justification,
    filing references, statutory deadline, assignee, etc.) live on
    ``VatWorkItemResponse`` and are served by ``GET /vat/work-items/{id}``.
    """

    id: int
    client_record_id: int
    office_client_number: int | None = None  # enriched by service
    client_name: str | None = None  # enriched by service
    client_id_number: str | None = None  # enriched by service
    period: str
    period_type: VatType
    status: VatWorkItemStatus
    net_vat: ApiDecimal
    final_vat_amount: ApiDecimal | None = None
    is_overridden: bool
    filed_at: ApiDateTime | None = None
    updated_at: ApiDateTime
    # Derived deadline fields shown in the "מועד הגשה" column
    submission_deadline: date | None = None
    extended_deadline: date | None = None
    days_until_deadline: int | None = None
    is_overdue: bool | None = None
    available_actions: list[ActionDescriptor] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class VatWorkItemListResponse(PaginatedResponse[VatWorkItemListItem]):
    pass


class VatWorkItemStatusSummaryResponse(BaseModel):
    pending_materials: int = 0
    material_received: int = 0
    data_entry_in_progress: int = 0
    ready_for_review: int = 0
    filed: int = 0
    canceled: int = 0


class VatGroupPeriod(BaseModel):
    period: str
    period_type: VatType


class VatWorkItemGroupSummary(BaseModel):
    group_key: str
    due_date: date
    period: str
    period_type: VatType
    periods: list[VatGroupPeriod]
    total_count: int
    filed_count: int
    pending_count: int
    not_filed_count: int
    overdue_count: int


class VatWorkItemGroupsResponse(BaseModel):
    groups: list[VatWorkItemGroupSummary]


class VatWorkItemGroupItemsResponse(BaseModel):
    items: list[VatWorkItemListItem]
    total: int
    period: str


class VatPeriodOptionResponse(BaseModel):
    period: str
    label: str
    start_month: int
    end_month: int
    is_opened: bool


class VatPeriodOptionsResponse(BaseModel):
    client_record_id: int
    year: int
    period_type: VatType
    options: list[VatPeriodOptionResponse]


class VatDeductionCategoryMetadata(BaseModel):
    category: str
    rate: float = Field(ge=0, le=1)
    label: str
    condition: str


class VatDeductionMetadataResponse(BaseModel):
    categories: list[VatDeductionCategoryMetadata]


# ── Status transitions ────────────────────────────────────────────────────────


class SendBackForCorrectionRequest(BaseModel):
    correction_note: str = Field(min_length=1, max_length=1000)

    @field_validator("correction_note")
    @classmethod
    def validate_correction_note(cls, v: str) -> str:
        normalized = v.strip()
        if not normalized:
            raise ValueError("נדרש טקסט תיקון")
        return normalized


# ── Filing ────────────────────────────────────────────────────────────────────


class VatWorkItemLookupResponse(BaseModel):
    id: int
    status: VatWorkItemStatus
    period: str

    model_config = {"from_attributes": True}


class FileVatReturnRequest(BaseModel):
    submission_method: SubmissionMethod  # שם חדש — תואם המודל
    override_amount: ApiDecimal | None = None
    override_justification: str | None = None
    submission_reference: str | None = None
    is_amendment: bool = False
    amends_item_id: int | None = None
