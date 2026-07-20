from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.charges.charge_constants import MONTHS_COVERED_MAX
from app.charges.charge_messages import CHARGE_FIELD_NOT_NULLABLE
from app.charges.models.charge import ChargeStatus, ChargeType
from app.core.action_schemas import ActionDescriptor
from app.core.api_types import ApiDateTime, ApiDecimal, PaginatedResponse, PeriodStr


class ChargeCreateRequest(BaseModel):
    client_record_id: int
    business_id: int | None = None
    amount: ApiDecimal = Field(gt=0)
    charge_type: ChargeType  # enum — לא str חופשי
    period: PeriodStr | None = None  # "YYYY-MM"
    months_covered: int = Field(1, ge=1, le=MONTHS_COVERED_MAX)  # monthly or bimonthly


class ChargeUpdateRequest(BaseModel):
    """Partial update for a draft charge.

    Routes pass ``model_dump(exclude_unset=True)`` so an omitted field is left
    untouched, while an explicit ``business_id: null`` clears the business scope.
    """

    business_id: int | None = None
    amount: ApiDecimal | None = Field(None, gt=0)
    charge_type: ChargeType | None = None
    period: PeriodStr | None = None
    months_covered: int | None = Field(None, ge=1, le=MONTHS_COVERED_MAX)
    description: str | None = None

    @field_validator("amount", "charge_type", "months_covered")
    @classmethod
    def _reject_explicit_null(cls, value: object) -> object:
        """These map to NOT NULL columns, so an explicit null is a client error.

        Defaults are not validated, so an omitted field still reaches the service
        as "unset" and is left untouched.
        """
        if value is None:
            raise ValueError(CHARGE_FIELD_NOT_NULLABLE)
        return value


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


class ChargeListResponse(PaginatedResponse[ChargeListItem]):
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
