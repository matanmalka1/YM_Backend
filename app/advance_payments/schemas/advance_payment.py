from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.advance_payments.advance_payment_constants import (
    BIMONTHLY_START_MONTHS,
    MAX_BULK_REFRESH_PAYMENTS,
    SUPPORTED_PERIOD_MONTH_COUNTS,
)
from app.advance_payments.models.advance_payment import (
    AdvancePaymentStatus,
    PaymentMethod,
    TurnoverSource,
)
from app.advance_payments.repositories.advance_payment_turnover_lookup_repository import (
    TurnoverResolution,
)
from app.common.period_utils import parse_period_month
from app.core.api_types import ApiDateTime, ApiDecimal, PaginatedResponse, PeriodStr
from app.core.schemas.validation import NonEmptyUpdateMixin
from app.utils.time_utils import israel_today


class AvailableTurnover(BaseModel):
    """VAT turnover this period *could* be snapshotted from.

    Not the payment's turnover. It is a discovery signal for an action the
    advisor has not taken yet, and it feeds no amount on the record: only the
    stored ``turnover_amount`` drives ``calculated_amount``/``expected_amount``.
    """

    amount: ApiDecimal
    source: Literal[TurnoverSource.VAT_FILED, TurnoverSource.VAT_PENDING]

    @classmethod
    def from_resolution(cls, resolution: TurnoverResolution | None) -> AvailableTurnover | None:
        if resolution is None or not resolution.is_resolved:
            return None
        return cls(amount=resolution.amount, source=resolution.source)


class AdvancePaymentRow(BaseModel):
    id: int
    client_record_id: int
    period: str
    period_months_count: int
    due_date: date
    due_date_effective: date | None = None
    expected_amount: ApiDecimal
    paid_amount: ApiDecimal
    status: AdvancePaymentStatus
    paid_at: ApiDateTime | None = None
    payment_method: PaymentMethod | None = None
    annual_report_id: int | None = None
    notes: str | None = None
    turnover_amount: ApiDecimal | None = None
    turnover_source: TurnoverSource | None = None
    turnover_snapshot_at: ApiDateTime | None = None
    advance_rate: ApiDecimal | None = None
    calculated_amount: ApiDecimal
    override_amount: ApiDecimal | None = None
    available_turnover: AvailableTurnover | None = None  # populated by router, not ORM
    missing_turnover: bool = False
    created_at: ApiDateTime
    updated_at: ApiDateTime | None = None

    @computed_field(return_type=ApiDecimal)
    @property
    def delta(self) -> Decimal:
        return self.expected_amount - self.paid_amount

    @computed_field
    @property
    def timing_status(self) -> Literal["overdue", "on_time"]:
        effective = self.due_date_effective or self.due_date
        if self.status != AdvancePaymentStatus.PAID and israel_today() > effective:
            return "overdue"
        return "on_time"

    @computed_field
    @property
    def paid_late(self) -> bool:
        if self.paid_at is None or self.status != AdvancePaymentStatus.PAID:
            return False
        paid_date = self.paid_at.date() if isinstance(self.paid_at, datetime) else self.paid_at
        effective = self.due_date_effective or self.due_date
        return paid_date > effective

    model_config = {"from_attributes": True, "use_enum_values": True}


class AdvancePaymentListResponse(PaginatedResponse[AdvancePaymentRow]):
    pass


class AdvancePaymentCreateRequest(BaseModel):
    period: PeriodStr
    period_months_count: int | None = Field(None, ge=1, le=2)
    turnover_amount: ApiDecimal | None = Field(None, ge=0)
    advance_rate: ApiDecimal | None = Field(None, ge=0)
    override_amount: ApiDecimal | None = Field(None, ge=0)
    paid_amount: ApiDecimal | None = Field(None, ge=0)
    payment_method: PaymentMethod | None = None
    annual_report_id: int | None = None
    notes: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def validate_period_for_frequency(self) -> AdvancePaymentCreateRequest:
        if self.period_months_count is None:
            return self
        if self.period_months_count not in SUPPORTED_PERIOD_MONTH_COUNTS:
            raise ValueError("period_months_count לא נתמך")
        if self.period_months_count != 2:
            return self

        month = parse_period_month(self.period)
        if month not in BIMONTHLY_START_MONTHS:
            raise ValueError("מקדמה דו-חודשית חייבת להתחיל בחודש אי-זוגי")
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "period": "2026-03",
                "period_months_count": 1,
                "turnover_amount": "50000.00",
                "advance_rate": "2.5",
            }
        }
    }


class AdvancePaymentUpdateRequest(NonEmptyUpdateMixin):
    paid_amount: ApiDecimal | None = Field(None, ge=0)
    expected_amount: ApiDecimal | None = Field(None, ge=0)
    paid_at: ApiDateTime | None = None
    payment_method: PaymentMethod | None = None
    notes: str | None = Field(None, max_length=500)
    turnover_amount: ApiDecimal | None = Field(None, ge=0)
    override_amount: ApiDecimal | None = Field(None, ge=0)

    @model_validator(mode="after")
    def _reject_null_for_required(self) -> AdvancePaymentUpdateRequest:
        # paid_amount/expected_amount are non-nullable columns.
        for field in ("paid_amount", "expected_amount"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"השדה {field} לא יכול להיות null")
        return self


class AdvancePaymentOverviewRow(BaseModel):
    id: int
    client_record_id: int
    office_client_number: int | None = None
    client_name: str
    id_number: str | None = None
    period: str
    period_months_count: int
    due_date: date
    due_date_effective: date | None = None
    expected_amount: ApiDecimal
    paid_amount: ApiDecimal
    status: AdvancePaymentStatus
    payment_method: PaymentMethod | None = None
    turnover_amount: ApiDecimal | None = None
    turnover_source: TurnoverSource | None = None
    turnover_snapshot_at: ApiDateTime | None = None
    calculated_amount: ApiDecimal
    override_amount: ApiDecimal | None = None
    available_turnover: AvailableTurnover | None = None  # populated by service, not ORM
    missing_turnover: bool = False
    advance_rate: ApiDecimal | None = None  # snapshot from payment

    @computed_field(return_type=ApiDecimal)
    @property
    def delta(self) -> Decimal:
        return self.expected_amount - self.paid_amount

    @computed_field
    @property
    def timing_status(self) -> Literal["overdue", "on_time"]:
        effective = self.due_date_effective or self.due_date
        if self.status != AdvancePaymentStatus.PAID and israel_today() > effective:
            return "overdue"
        return "on_time"

    model_config = {"from_attributes": False, "use_enum_values": True}


class AdvancePaymentOverviewResponse(PaginatedResponse[AdvancePaymentOverviewRow]):
    total_expected: ApiDecimal | None = None
    total_paid: ApiDecimal | None = None
    collection_rate: ApiDecimal | None = None  # 0.00–100.00


class AnnualKPIResponse(BaseModel):
    client_record_id: int
    year: int
    total_expected: ApiDecimal
    total_paid: ApiDecimal
    collection_rate: ApiDecimal  # 0.00–100.00
    overdue_count: int
    on_time_count: int


class MonthBatchSummary(BaseModel):
    year: int
    month: int
    due_date: date | None = None
    period_months_count: int = 1
    client_count: int
    missing_turnover_count: int
    overdue_count: int
    pending_count: int = 0
    paid_count: int = 0
    not_paid_count: int = 0
    due_this_month_count: int = 0
    total_expected: ApiDecimal | None = None
    total_paid: ApiDecimal | None = None
    collection_rate: ApiDecimal = Decimal("0")


class GenerateScheduleRequest(BaseModel):
    year: int
    period_months_count: int | None = Field(None, ge=1, le=2)
    reference_date: date | None = Field(
        None,
        description=("אם מסופק, ידלג על תקופות שתאריך היעד שלהן קודם לתאריך זה. ברירת מחדל: היום."),
    )


class GenerateScheduleResponse(BaseModel):
    created: int
    skipped: int


class RefreshTurnoverRequest(BaseModel):
    confirm_pending: bool = Field(
        False,
        description="אשר קיבוע מחזור מדוח מע״מ שטרם הוגש",
    )


class BulkRefreshTurnoverRequest(BaseModel):
    """Explicit ids only: the caller states exactly which periods it is writing to.

    There is deliberately no filter-based form — a filter can match rows the
    advisor never saw, and this command writes to every row it matches.
    """

    payment_ids: list[int] = Field(..., min_length=1, max_length=MAX_BULK_REFRESH_PAYMENTS)

    @field_validator("payment_ids")
    @classmethod
    def _reject_duplicates(cls, ids: list[int]) -> list[int]:
        # A duplicated id means the caller's view of the batch is wrong;
        # silently deduplicating would hide that bug, so fail the request.
        if len(set(ids)) != len(ids):
            raise ValueError("payment_ids מכיל מזהים כפולים")
        return ids


class BulkRefreshTurnoverResponse(BaseModel):
    refreshed: int
    skipped_no_vat: int
    skipped_not_filed: int
    skipped_paid: int
