from typing import Literal

from pydantic import BaseModel, Field

from app.charges.models.charge import ChargeStatus, ChargeType
from app.charges.services.constants import MONTHS_COVERED_MAX
from app.core.action_schemas import ActionDescriptor
from app.core.api_types import ApiDateTime, ApiDecimal, PaginatedResponse, PeriodStr


class ChargeCreateRequest(BaseModel):
    client_record_id: int
    business_id: int | None = None
    amount: ApiDecimal = Field(gt=0)
    charge_type: ChargeType  # enum — לא str חופשי
    period: PeriodStr | None = None  # "YYYY-MM"
    months_covered: int = Field(1, ge=1, le=MONTHS_COVERED_MAX)  # monthly or bimonthly


class ChargeResponse(BaseModel):
    id: int
    client_record_id: int
    client_name: str | None = None
    office_client_number: int | None = None
    business_id: int | None = None
    business_name: str | None = None  # enriched by service
    annual_report_id: int | None = None
    charge_type: ChargeType
    status: ChargeStatus
    amount: ApiDecimal
    period: str | None = None
    months_covered: int
    description: str | None = None
    created_at: ApiDateTime
    updated_at: ApiDateTime | None = None
    created_by: int | None = None
    issued_at: ApiDateTime | None = None
    issued_by: int | None = None
    paid_at: ApiDateTime | None = None
    paid_by: int | None = None
    canceled_at: ApiDateTime | None = None
    canceled_by: int | None = None
    cancellation_reason: str | None = None
    available_actions: list[ActionDescriptor] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ChargeListItem(BaseModel):
    """Thin DTO for the charges list/table rows.

    Contains only fields rendered by the charges table (``ChargeColumns``,
    ``ChargeClientCell``). Detail-only fields (description, audit actors,
    cancellation reason, annual_report_id) stay on ``ChargeResponse`` and are
    served by ``GET /charges/{id}``.
    """

    id: int
    client_record_id: int
    client_name: str | None = None
    office_client_number: int | None = None
    business_id: int | None = None
    business_name: str | None = None
    charge_type: ChargeType
    status: ChargeStatus
    amount: ApiDecimal
    period: str | None = None
    months_covered: int
    created_at: ApiDateTime
    issued_at: ApiDateTime | None = None
    paid_at: ApiDateTime | None = None
    available_actions: list[ActionDescriptor] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ChargeCancelRequest(BaseModel):
    reason: str | None = None


class ChargeStatusStat(BaseModel):
    count: int = 0
    amount: ApiDecimal = ApiDecimal("0")


class ChargeListStats(BaseModel):
    draft: ChargeStatusStat = ChargeStatusStat()
    issued: ChargeStatusStat = ChargeStatusStat()
    paid: ChargeStatusStat = ChargeStatusStat()
    canceled: ChargeStatusStat = ChargeStatusStat()


class ChargeListResponse(BaseModel):
    items: list[ChargeListItem]
    page: int
    page_size: int
    total: int
    stats: ChargeListStats


class ChargeResponseListResponse(PaginatedResponse[ChargeResponse]):
    pass


class BulkChargeActionRequest(BaseModel):
    charge_ids: list[int] = Field(min_length=1)
    action: Literal["issue", "mark-paid", "cancel"]
    cancellation_reason: str | None = None


class BulkChargeFailedItem(BaseModel):
    id: int
    error: str


class BulkChargeActionResponse(BaseModel):
    succeeded: list[int]
    failed: list[BulkChargeFailedItem]
