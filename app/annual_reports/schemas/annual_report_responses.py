from pydantic import BaseModel

from app.annual_reports.models.annual_report_enums import (
    AnnualReportSchedule,
    ClientAnnualFilingType,
    ExtensionReason,
    FilingDeadlineType,
    PrimaryAnnualReportForm,
    SubmissionMethod,
)
from app.common.enums import ObligationStatus
from app.core.api_types import ApiDateTime, ApiDecimal, PaginatedResponse


class AnnualReportResponse(BaseModel):
    id: int
    client_record_id: int
    office_client_number: int | None = None
    client_name: str | None = None
    client_id_number: str | None = None
    tax_year: int
    client_type: ClientAnnualFilingType
    form_type: PrimaryAnnualReportForm
    status: ObligationStatus
    deadline_type: FilingDeadlineType
    filing_deadline: ApiDateTime | None = None
    is_overdue: bool = False
    days_until_deadline: int | None = None
    custom_deadline_note: str | None = None
    closed_at: ApiDateTime | None = None
    closed_by: int | None = None
    closed_late: bool | None = None  # NULL = no deadline at close (D-32), never False
    ita_reference: str | None = None
    assessment_amount: ApiDecimal | None = None
    refund_due: ApiDecimal | None = None
    tax_due: ApiDecimal | None = None
    has_rental_income: bool = False
    has_capital_gains: bool = False
    has_foreign_income: bool = False
    has_depreciation: bool = False
    submission_method: SubmissionMethod | None = None
    extension_reason: ExtensionReason | None = None
    notes: str | None = None
    created_at: ApiDateTime
    updated_at: ApiDateTime
    assigned_to: int | None = None
    created_by: int
    available_transitions: list[ObligationStatus] = []

    model_config = {"from_attributes": True}


class AnnualReportListItem(BaseModel):
    """Thin row DTO for annual-report list/card endpoints.

    Only fields rendered by list/history/comparison UIs. Detail-only,
    calculation, action, and transition fields are intentionally excluded
    (see AnnualReportDetailResponse for the full detail shape).
    """

    id: int
    client_record_id: int
    office_client_number: int | None = None
    client_name: str | None = None
    client_id_number: str | None = None
    tax_year: int
    client_type: ClientAnnualFilingType
    form_type: PrimaryAnnualReportForm
    status: ObligationStatus
    deadline_type: FilingDeadlineType
    filing_deadline: ApiDateTime | None = None
    is_overdue: bool = False
    days_until_deadline: int | None = None
    closed_at: ApiDateTime | None = None
    assessment_amount: ApiDecimal | None = None
    refund_due: ApiDecimal | None = None
    tax_due: ApiDecimal | None = None

    model_config = {"from_attributes": True}


class AnnualReportListResponse(PaginatedResponse[AnnualReportListItem]):
    pass


class ScheduleEntryResponse(BaseModel):
    id: int
    annual_report_id: int
    schedule: AnnualReportSchedule
    is_required: bool
    is_complete: bool
    notes: str | None = None
    created_at: ApiDateTime
    completed_at: ApiDateTime | None = None
    completed_by: int | None = None

    model_config = {"from_attributes": True}


class AnnualReportScheduleListResponse(PaginatedResponse[ScheduleEntryResponse]):
    pass


class AnnualReportTaxCalculationResponse(BaseModel):
    """Computed financial/tax outputs for a report detail view.

    Every field here is derived/aggregated in the service (financial summary,
    tax engine, credit-point breakdown, advances). User-entered deduction
    inputs (pension_contribution, donation_amount, other_credits) and the
    persisted outcome columns (refund_due, tax_due, assessment_amount) stay
    flat on AnnualReportDetailResponse.
    """

    # סיכום פיננסי — מ-FinancialSummaryService
    total_income: ApiDecimal | None = None
    total_expenses: ApiDecimal | None = None
    recognized_expenses: ApiDecimal | None = None
    taxable_income: ApiDecimal | None = None
    # מנוע המס / מקדמות
    profit: ApiDecimal | None = None
    tax_after_credits: ApiDecimal | None = None
    final_balance: ApiDecimal | None = None
    credit_points_value: ApiDecimal | None = None
    donation_credit: ApiDecimal | None = None
    # נקודות זיכוי — מצרף מ-AnnualReportCreditPointRepository
    credit_points: ApiDecimal | None = None
    pension_credit_points: ApiDecimal | None = None
    life_insurance_credit_points: ApiDecimal | None = None
    tuition_credit_points: ApiDecimal | None = None


class AnnualReportDetailResponse(AnnualReportResponse):
    schedules: list[ScheduleEntryResponse] = []
    # ניכויים שמוזנים ידנית — מ-AnnualReportDetail
    pension_contribution: ApiDecimal | None = None
    donation_amount: ApiDecimal | None = None
    other_credits: ApiDecimal | None = None
    internal_notes: str | None = None
    amendment_reason: str | None = None
    # חישובי מס מקובצים
    tax_calculation: AnnualReportTaxCalculationResponse | None = None


class SeasonSummaryResponse(BaseModel):
    tax_year: int
    filing_season_year: int
    total: int
    # One field per stage of the shared obligation lifecycle. These used to be the
    # annual-report-only status names; four of them silently returned 0 once the
    # statuses merged, because the query keys by the stored value.
    awaiting_input: int
    input_received: int
    in_progress: int
    awaiting_verification: int
    submitted: int
    canceled: int = 0
    completion_rate: ApiDecimal
    overdue_count: int


class DefaultTaxYearResponse(BaseModel):
    tax_year: int
