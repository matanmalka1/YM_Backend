from __future__ import annotations

from pydantic import BaseModel, model_validator

from app.annual_reports.models.annual_report_enums import (
    AnnualReportSchedule,
    ClientAnnualFilingType,
    ExtensionReason,
    FilingDeadlineType,
    ReportStage,
    SubmissionMethod,
)
from app.common.enums import ObligationStatus
from app.core.api_types import ApiDateTime, ApiDecimal
from app.core.schemas.validation import NonEmptyUpdateMixin


class AnnualReportCreateRequest(BaseModel):
    client_record_id: int
    tax_year: int
    client_type: ClientAnnualFilingType
    deadline_type: FilingDeadlineType = FilingDeadlineType.STANDARD
    assigned_to: int | None = None
    notes: str | None = None
    submission_method: SubmissionMethod | None = None
    extension_reason: ExtensionReason | None = None
    has_rental_income: bool = False
    has_capital_gains: bool = False
    has_foreign_income: bool = False
    has_depreciation: bool = False


class AmendRequest(BaseModel):
    reason: str


class StatusTransitionRequest(BaseModel):
    status: ObligationStatus  # enum — לא str חופשי
    note: str | None = None
    ita_reference: str | None = None
    assessment_amount: ApiDecimal | None = None
    refund_due: ApiDecimal | None = None
    tax_due: ApiDecimal | None = None


class DeadlineUpdateRequest(NonEmptyUpdateMixin):
    # Partial update: deadline_type may be omitted (keeps existing type) when
    # only custom_deadline_note changes. Explicit null on deadline_type is
    # invalid (non-nullable column).
    deadline_type: FilingDeadlineType | None = None
    custom_deadline_note: str | None = None

    @model_validator(mode="after")
    def _reject_null_deadline_type(self) -> DeadlineUpdateRequest:
        if "deadline_type" in self.model_fields_set and self.deadline_type is None:
            raise ValueError("השדה deadline_type לא יכול להיות null")
        return self


class SubmitRequest(BaseModel):
    submitted_at: ApiDateTime | None = None
    ita_reference: str | None = None
    submission_method: SubmissionMethod | None = None
    note: str | None = None


class StageTransitionRequest(BaseModel):
    to_stage: ReportStage  # enum


class ScheduleAddRequest(BaseModel):
    schedule: AnnualReportSchedule  # enum
    notes: str | None = None


class ScheduleCompleteRequest(BaseModel):
    schedule: AnnualReportSchedule  # enum
