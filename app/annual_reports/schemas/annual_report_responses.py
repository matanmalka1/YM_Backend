from pydantic import BaseModel, Field

from app.annual_reports.models.annual_report_enums import (
    AnnualReportSchedule,
    AnnualReportStatus,
    ClientAnnualFilingType,
    ExtensionReason,
    FilingDeadlineType,
    PrimaryAnnualReportForm,
    SubmissionMethod,
)
from app.core.action_schemas import ActionDescriptor
from app.core.api_types import ApiDateTime, ApiDecimal, PaginatedResponse


class AnnualReportResponse(BaseModel):
    id: int
    client_record_id: int
    office_client_number: int | None = None
    client_name: str | None = None
    client_id_number: str | None = None
    business_name: str | None = None
    tax_year: int
    client_type: ClientAnnualFilingType
    form_type: PrimaryAnnualReportForm
    status: AnnualReportStatus
    deadline_type: FilingDeadlineType
    filing_deadline: ApiDateTime | None = None
    custom_deadline_note: str | None = None
    submitted_at: ApiDateTime | None = None
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
    available_actions: list[ActionDescriptor] = Field(default_factory=list)
    available_transitions: list[AnnualReportStatus] = []

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
    status: AnnualReportStatus
    deadline_type: FilingDeadlineType
    filing_deadline: ApiDateTime | None = None
    submitted_at: ApiDateTime | None = None
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


class AnnualReportAuditEntry(BaseModel):
    id: int
    annual_report_id: int
    from_status: AnnualReportStatus | None = None
    to_status: AnnualReportStatus
    changed_by: int
    note: str | None = None
    occurred_at: ApiDateTime

    model_config = {"from_attributes": True}


class AnnualReportAuditListResponse(PaginatedResponse[AnnualReportAuditEntry]):
    pass


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
    # נקודות זיכוי — מצרף מ-AnnualReportCreditPointRepository
    credit_points: ApiDecimal | None = None
    pension_credit_points: ApiDecimal | None = None
    life_insurance_credit_points: ApiDecimal | None = None
    tuition_credit_points: ApiDecimal | None = None


class AnnualReportDetailResponse(AnnualReportResponse):
    schedules: list[ScheduleEntryResponse] = []
    status_audit: list[AnnualReportAuditEntry] = []
    # ניכויים שמוזנים ידנית — מ-AnnualReportDetail
    pension_contribution: ApiDecimal | None = None
    donation_amount: ApiDecimal | None = None
    other_credits: ApiDecimal | None = None
    client_approved_at: ApiDateTime | None = None
    internal_notes: str | None = None
    amendment_reason: str | None = None
    # חישובי מס מקובצים
    tax_calculation: AnnualReportTaxCalculationResponse | None = None


class SeasonSummaryResponse(BaseModel):
    tax_year: int
    filing_season_year: int
    total: int
    not_started: int
    collecting_docs: int
    in_preparation: int
    pending_client: int
    submitted: int
    closed: int
    canceled: int = 0
    completion_rate: ApiDecimal
    overdue_count: int


class DefaultTaxYearResponse(BaseModel):
    tax_year: int
