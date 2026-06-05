from datetime import date

from pydantic import BaseModel

from app.annual_reports.models.annual_report_enums import (
    AnnualReportStatus,
    PrimaryAnnualReportForm,
)
from app.core.api_types import ApiDecimal


class VatComplianceReportItemResponse(BaseModel):
    client_record_id: int
    client_name: str
    year: int
    period_type: str
    grouping_key: str
    periods_expected: int
    periods_filed: int
    periods_open: int
    on_time_count: int
    late_count: int
    compliance_rate: float


class VatComplianceStalePendingResponse(BaseModel):
    client_record_id: int
    client_name: str
    period: str
    days_pending: int


class VatComplianceReportResponse(BaseModel):
    year: int
    total_clients: int
    items: list[VatComplianceReportItemResponse]
    stale_pending: list[VatComplianceStalePendingResponse]


class AdvancePaymentReportItemResponse(BaseModel):
    client_record_id: int
    office_client_number: int | None = None
    client_name: str
    total_expected: ApiDecimal
    total_paid: ApiDecimal
    overdue_count: int
    gap: ApiDecimal


class AdvancePaymentCollectionsReportResponse(BaseModel):
    year: int
    month: int | None = None
    total_expected: ApiDecimal
    total_paid: ApiDecimal
    collection_rate: float
    total_gap: ApiDecimal
    items: list[AdvancePaymentReportItemResponse]


class AnnualReportStatusClientResponse(BaseModel):
    client_record_id: int
    client_name: str
    form_type: PrimaryAnnualReportForm | None = None
    filing_deadline: date | None = None
    days_until_deadline: int | None = None


class AnnualReportStatusGroupResponse(BaseModel):
    status: AnnualReportStatus
    count: int
    clients: list[AnnualReportStatusClientResponse]


class AnnualReportStatusReportResponse(BaseModel):
    tax_year: int
    total: int
    statuses: list[AnnualReportStatusGroupResponse]


class AgingReportItemResponse(BaseModel):
    client_record_id: int
    client_name: str
    total_outstanding: ApiDecimal
    current: ApiDecimal
    days_30: ApiDecimal
    days_60: ApiDecimal
    days_90_plus: ApiDecimal
    oldest_invoice_date: date | None = None
    oldest_invoice_days: int | None = None


class AgingReportSummaryResponse(BaseModel):
    total_clients: int
    total_current: ApiDecimal
    total_30_days: ApiDecimal
    total_60_days: ApiDecimal
    total_90_plus: ApiDecimal


class AgingReportResponse(BaseModel):
    report_date: date
    total_outstanding: ApiDecimal
    items: list[AgingReportItemResponse]
    summary: AgingReportSummaryResponse
    capped: bool
    cap_limit: int
