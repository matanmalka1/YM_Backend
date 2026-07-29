from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.advance_payments.advance_payment_constants import (
    MAX_BULK_MARK_PAID_PAYMENTS,
    MAX_BULK_REFRESH_PAYMENTS,
    VAT_TURNOVER_MISMATCH_TOLERANCE,
)
from app.advance_payments.models.advance_payment import (
    ObligationStatus,
    PaymentMethod,
    TurnoverSource,
)
from app.advance_payments.repositories.advance_payment_turnover_lookup_repository import (
    TurnoverResolution,
)
from app.common.obligation_closing import ClosingReadiness
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


class VatTurnoverMismatch(BaseModel):
    """The stored turnover disagrees with the period's current VAT figure.

    Computed server-side against ``VAT_TURNOVER_MISMATCH_TOLERANCE`` — the
    frontend must render, never re-derive. ``None`` on a row means "no
    disagreement detectable": no stored turnover, no VAT return, or a
    difference within tolerance.
    """

    vat_amount: ApiDecimal
    difference: ApiDecimal
    source: Literal[TurnoverSource.VAT_FILED, TurnoverSource.VAT_PENDING]

    @classmethod
    def from_comparison(
        cls, stored_turnover, resolution: TurnoverResolution | None
    ) -> VatTurnoverMismatch | None:
        if stored_turnover is None or resolution is None or not resolution.is_resolved:
            return None
        difference = abs(Decimal(stored_turnover) - resolution.amount)
        if difference <= VAT_TURNOVER_MISMATCH_TOLERANCE:
            return None
        return cls(vat_amount=resolution.amount, difference=difference, source=resolution.source)


class AdvancePaymentRow(BaseModel):
    id: int
    client_record_id: int
    assigned_to: int | None = None
    period: str
    period_months_count: int
    due_date: date
    due_date_effective: date | None = None
    expected_amount: ApiDecimal
    paid_amount: ApiDecimal
    status: ObligationStatus
    paid_at: ApiDateTime | None = None
    payment_method: PaymentMethod | None = None
    payment_reference: str | None = None
    # Closing facts — written once when the advisor closes the period (D-13/D-20).
    closed_at: ApiDateTime | None = None
    closed_by: int | None = None
    closed_late: bool | None = None
    # The period's answer, not this row's (D-34). An amendment has no due date,
    # so its own `closed_late` is NULL — but the period it corrects may have been
    # filed late, and that fact must survive the correction.
    chain_closed_late: bool | None = None
    # Amendment chain (D-10/D-12). `amends_id` set => this record corrects
    # another; `superseded_at` set => a later record corrects this one.
    amends_id: int | None = None
    superseded_at: ApiDateTime | None = None
    annual_report_id: int | None = None
    notes: str | None = None
    turnover_amount: ApiDecimal | None = None
    turnover_source: TurnoverSource | None = None
    turnover_snapshot_at: ApiDateTime | None = None
    advance_rate: ApiDecimal | None = None
    calculated_amount: ApiDecimal
    override_amount: ApiDecimal | None = None
    withheld_amount: ApiDecimal | None = None
    available_turnover: AvailableTurnover | None = None  # populated by router, not ORM
    vat_turnover_mismatch: VatTurnoverMismatch | None = None  # populated by router, not ORM
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
        if self.status != ObligationStatus.SUBMITTED and israel_today() > effective:
            return "overdue"
        return "on_time"

    model_config = {"from_attributes": True, "use_enum_values": True}


class AdvancePaymentListResponse(PaginatedResponse[AdvancePaymentRow]):
    pass


class AdvancePaymentCreateRequest(BaseModel):
    period: PeriodStr
    period_months_count: int | None = Field(None, ge=1, le=2)
    assigned_to: int | None = None
    turnover_amount: ApiDecimal | None = Field(None, ge=0)
    advance_rate: ApiDecimal | None = Field(None, ge=0)
    override_amount: ApiDecimal | None = Field(None, ge=0)
    withheld_amount: ApiDecimal | None = Field(None, ge=0)
    paid_amount: ApiDecimal | None = Field(None, ge=0)
    payment_method: PaymentMethod | None = None
    payment_reference: str | None = Field(None, max_length=100)
    annual_report_id: int | None = None
    notes: str | None = Field(None, max_length=500)

    # Bi-monthly alignment is not re-validated here: the single gate is
    # TaxCalendarMaterializationService, which answers for every caller — not only
    # requests that arrive through this schema.

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
    payment_reference: str | None = Field(None, max_length=100)
    notes: str | None = Field(None, max_length=500)
    turnover_amount: ApiDecimal | None = Field(None, ge=0)
    override_amount: ApiDecimal | None = Field(None, ge=0)
    withheld_amount: ApiDecimal | None = Field(None, ge=0)
    assigned_to: int | None = None

    @model_validator(mode="after")
    def _reject_null_for_required(self) -> AdvancePaymentUpdateRequest:
        # paid_amount/expected_amount are non-nullable columns.
        for field in ("paid_amount", "expected_amount"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"השדה {field} לא יכול להיות null")
        return self


class AdvancePaymentClosingReadinessResponse(ClosingReadiness):
    """The shared closing-gate shape (§4.1.8) for an advance payment."""

    advance_payment_id: int


class AdvancePaymentStatusTransitionRequest(BaseModel):
    status: ObligationStatus
    note: str | None = None


class AdvancePaymentDeleteRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("נדרשת סיבת מחיקה")
        return stripped


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
    status: ObligationStatus
    payment_method: PaymentMethod | None = None
    payment_reference: str | None = None
    turnover_amount: ApiDecimal | None = None
    turnover_source: TurnoverSource | None = None
    turnover_snapshot_at: ApiDateTime | None = None
    calculated_amount: ApiDecimal
    override_amount: ApiDecimal | None = None
    available_turnover: AvailableTurnover | None = None  # populated by service, not ORM
    vat_turnover_mismatch: VatTurnoverMismatch | None = None  # populated by service, not ORM
    missing_turnover: bool = False
    advance_rate: ApiDecimal | None = None  # snapshot from payment
    withheld_amount: ApiDecimal | None = None

    @computed_field(return_type=ApiDecimal)
    @property
    def delta(self) -> Decimal:
        return self.expected_amount - self.paid_amount

    @computed_field
    @property
    def timing_status(self) -> Literal["overdue", "on_time"]:
        effective = self.due_date_effective or self.due_date
        if self.status != ObligationStatus.SUBMITTED and israel_today() > effective:
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
    vat_mismatch_count: int = 0
    overdue_count: int
    pending_count: int = 0
    paid_count: int = 0
    not_paid_count: int = 0
    due_this_month_count: int = 0
    total_expected: ApiDecimal | None = None
    total_paid: ApiDecimal | None = None
    collection_rate: ApiDecimal = Decimal("0")


class StaleCadenceSummary(BaseModel):
    """Superseded-cadence rows standing in the new schedule's way.

    ``pending`` is what a confirmed cleanup would remove (or has just removed,
    reported as ``removed``); ``settled`` is what it never will.
    """

    removed: int = 0
    pending: int = 0
    settled: int = 0


_CLEANUP_STALE_CADENCE_FIELD = Field(
    False,
    description=(
        "מחק מקדמות עתידיות שטרם שולמו שנוצרו בתדירות הקודמת של הלקוח, "
        "כדי שהלוח החדש ייווצר במקומן. ברירת מחדל: לא מוחק."
    ),
)


class GenerateScheduleRequest(BaseModel):
    year: int
    period_months_count: int | None = Field(None, ge=1, le=2)
    reference_date: date | None = Field(
        None,
        description=("אם מסופק, ידלג על תקופות שתאריך היעד שלהן קודם לתאריך זה. ברירת מחדל: היום."),
    )
    cleanup_stale_cadence: bool = _CLEANUP_STALE_CADENCE_FIELD


class GenerateScheduleResponse(BaseModel):
    created: int
    skipped: int
    stale_cadence: StaleCadenceSummary


class IneligibleClient(BaseModel):
    client_record_id: int
    client_name: str
    reason: Literal["frequency_not_set"]


class BulkGeneratePreviewResponse(BaseModel):
    """What an office-wide generation would cover, before it runs.

    Serves the modal twice: the eligible count is the progress denominator
    shown up front, and ``ineligible`` is the exceptions list shown afterwards.
    """

    eligible_count: int
    ineligible: list[IneligibleClient]


class BulkGenerateRequest(BaseModel):
    year: int
    cursor: int | None = Field(
        None,
        description="מזהה הלקוח האחרון שעובד; השאר ריק בבקשה הראשונה של הריצה",
    )
    cleanup_stale_cadence: bool = _CLEANUP_STALE_CADENCE_FIELD


class BulkGenerateFailedClient(BaseModel):
    client_record_id: int
    client_name: str
    reason: str


class BulkGenerateResponse(BaseModel):
    """One chunk's outcome. The caller repeats while ``next_cursor`` is set."""

    clients_processed: int
    created: int
    skipped: int
    stale_cadence: StaleCadenceSummary
    failed: list[BulkGenerateFailedClient]
    next_cursor: int | None


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
    # Closed periods are immutable (D-13) — a bulk sweep skips them, never errors.
    skipped_closed: int


class BulkMarkPaidRequest(BaseModel):
    """Explicit ids only — same principle as ``BulkRefreshTurnoverRequest``.

    Marks each listed payment as paid in full: ``paid_amount`` is topped up to
    ``expected_amount`` (partial payments included — the client settled the
    difference). Fully-paid rows are skipped, never rewritten.
    """

    payment_ids: list[int] = Field(..., min_length=1, max_length=MAX_BULK_MARK_PAID_PAYMENTS)
    paid_at: ApiDateTime | None = Field(None, description="ברירת מחדל: עכשיו")
    payment_method: PaymentMethod | None = None
    reference_prefix: str | None = Field(
        None,
        max_length=80,
        description="אם סופק, כל רשומה תקבל אסמכתא בצורת '<prefix>-<payment_id>'",
    )

    @field_validator("payment_ids")
    @classmethod
    def _reject_duplicates(cls, ids: list[int]) -> list[int]:
        if len(set(ids)) != len(ids):
            raise ValueError("payment_ids מכיל מזהים כפולים")
        return ids


class BulkMarkPaidSkippedItem(BaseModel):
    id: int
    # "closed": the period is submitted/canceled and immutable (D-13).
    reason: Literal["already_paid", "no_amount", "not_found", "closed"]


class BulkMarkPaidResponse(BaseModel):
    updated: list[int]
    skipped: list[BulkMarkPaidSkippedItem]


class BulkRateUpdateRequest(BaseModel):
    advance_rate: ApiDecimal = Field(ge=0, le=100)
    from_period: PeriodStr


class BulkRateUpdateResponse(BaseModel):
    # Repriced PENDING rows vs. rows left as-is (partial/paid at or after the period).
    updated: int
    skipped: int
